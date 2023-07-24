#!/usr/bin/env python3

import argparse
import os
import re
import time
from pprint import pprint

import requests
import urllib3
import validators
from azure.identity import AzureCliCredential
from azure.mgmt.dns import DnsManagementClient
from dotenv import load_dotenv

urllib3.disable_warnings()
load_dotenv()

parser = argparse.ArgumentParser(
    description="")

parser.add_argument("domain_name",
                    action="store",
                    nargs=None,
                    const=None,
                    default=None,
                    type=str,
                    choices=None,
                    help="domain name",
                    metavar=None)

parser.add_argument("-a", "--a-record",
                    action="store",
                    nargs=None,
                    const=None,
                    default="127.0.0.1",
                    type=str,
                    choices=None,
                    help="A record",
                    metavar=None)

parser.add_argument("-aaaa", "--aaaa-record",
                    action="store",
                    nargs=None,
                    const=None,
                    default=None,
                    type=str,
                    choices=None,
                    help="AAAA record",
                    metavar=None)

parser.add_argument("--ttl",
                    action="store",
                    nargs=None,
                    const=None,
                    default=3600,
                    type=int,
                    choices=None,
                    help="TTL",
                    metavar=None)

args = parser.parse_args()

def main(args):
    result_validation = validators.domain(args.domain_name)
    if args.domain_name is None or result_validation != True:
        print("[ERROR]", "Incorrect domain name.")
        return

    subscription_id = os.getenv("SUBSCRIPTION_ID", None)
    if subscription_id is None:
        print("[ERROR]", "Invalid subscription id.")
        return

    azure_cli = AzureCliCredential()

    dns_client = DnsManagementClient(
        azure_cli,
        subscription_id
    )

    execute(args, dns_client)

    dns_client.close()

def execute(args, dns_client):
    domain_name: str = args.domain_name
    subdomain: str = ""
    zone_name: str = None
    match = re.search(r"^(.*?)\.?([^\.]+\.[a-z]+)$", domain_name)
    if match:
        subdomain = match.group(1)
        zone_name = match.group(2)
    else:
        print("[ERROR]", "Incorrect domain name.")
        return

    sendgrid_api_key = os.getenv("SENDGRID_API_KEY", None)
    if sendgrid_api_key is None:
        print("[ERROR]", "Invalid Sendgrid API key.")
        return

    resource_group = os.getenv("RESOURCE_GROUP", None)
    if resource_group is None:
        print("[ERROR]", "Invalid resource group.")
        return

    headers = {
        "authorization" : "Bearer {:s}".format(sendgrid_api_key),
        "content-type" : "application/json"
    }

    domain_id: int = None

    idx : int = 0
    limit: int = 50
    while True:
        payload = {
            "domain" : domain_name,
            "limit" : limit,
            "offset" : idx
        }

        response = requests.get("https://api.sendgrid.com/v3/whitelabel/domains", headers=headers, params=payload)

        if response.status_code != 200:
            print("[ERROR]", "Unknown response.", "code:", response.status_code)
            return

        domain_list = response.json()
        if len(domain_list) == 0:
            break

        for domain in domain_list:
            if domain["domain"] == domain_name:
                domain_id = domain["id"]
                print("[INFO]", "Domain existence.", "id:", domain_id)
                break

        idx += limit

    # Azure DNSにzoneが存在するか確認
    dns_zone = None
    try:
        dns_zone = dns_client.zones.get(resource_group, zone_name)
    except Exception as ex:
        print("[ERROR]", ex)
        return

    # ドメインがSendgridになければ作成
    if domain_id is None:
        data = {
            "domain" : domain_name,
            "subdomain" : "",
            "automatic_security": False,
            "custom_spf": True,
            "default": False
        }

        response = requests.post("https://api.sendgrid.com/v3/whitelabel/domains", headers=headers, json=data)

        if response.status_code == 201:
            domain = response.json()
            domain_id = domain["id"]
            print("[INFO]", "Domain create.", "id:", domain_id)
        else:
            print("[ERROR]", "Unknown response.", "code:", response.status_code)
            return

    response = requests.get("https://api.sendgrid.com/v3/whitelabel/domains/{:d}".format(domain_id), headers=headers)
    if response.status_code != 200:
        print("[ERROR]", "Unknown response.", "code:", response.status_code)
        return
    domain = response.json()

    # Aレコード作成
    relative_record_set_name: str = "@"
    if subdomain != "":
        relative_record_set_name = subdomain

    create_dns_record(
        args,
        dns_client,
        resource_group,
        zone_name,
        relative_record_set_name,
        "A",
        {
            "ttl": args.ttl,
            "a_records": [
                {
                    "ipv4_address": args.a_record
                }
            ]
        }
    )

    # MXレコード作成
    create_dns_record(
        args,
        dns_client,
        resource_group,
        zone_name,
        relative_record_set_name,
        "MX",
        {
            "ttl": args.ttl,
            "mx_records": [
                {
                    "exchange": domain["dns"]["mail_server"]["data"],
                    "preference": 10
                }
            ]
        }
    )

    # MXレコード作成(Sendgrid)
    if domain["dns"]["mail_server"]["host"] != "":
        match = re.search(r"^(.*?)\.?[^\.]+\.[a-z]+$", domain["dns"]["mail_server"]["host"])
        if match:
            relative_record_set_name = match.group(1)

    create_dns_record(
        args,
        dns_client,
        resource_group,
        zone_name,
        relative_record_set_name,
        "MX",
        {
            "ttl": args.ttl,
            "mx_records": [
                {
                    "exchange": domain["dns"]["mail_server"]["data"],
                    "preference": 10
                }
            ]
        }
    )

    # TXTレコード(SPF)作成(Sendgrid)
    if domain["dns"]["subdomain_spf"]["host"] != "":
        match = re.search(r"^(.*?)\.?[^\.]+\.[a-z]+$", domain["dns"]["subdomain_spf"]["host"])
        if match:
            relative_record_set_name = match.group(1)

    create_dns_record(
        args,
        dns_client,
        resource_group,
        zone_name,
        relative_record_set_name,
        "TXT",
        {
            "ttl": args.ttl,
            "txt_records": [
                {
                    "value": [
                        domain["dns"]["subdomain_spf"]["data"]
                    ]
                }
            ]
        }
    )

    # TXTレコード(DKIM)作成(Sendgrid)
    if domain["dns"]["dkim"]["host"] != "":
        match = re.search(r"^(.*?)\.?[^\.]+\.[a-z]+$", domain["dns"]["dkim"]["host"])
        if match:
            relative_record_set_name = match.group(1)

    create_dns_record(
        args,
        dns_client,
        resource_group,
        zone_name,
        relative_record_set_name,
        "TXT",
        {
            "ttl": args.ttl,
            "txt_records": [
                {
                    "value": [
                        domain["dns"]["dkim"]["data"]
                    ]
                }
            ]
        }
    )

    #
    print("[NOTICE]", "wait... 10seconds")
    time.sleep(10)

    # Sendgrid Validate
    response = requests.post("https://api.sendgrid.com/v3/whitelabel/domains/{:d}/validate".format(domain_id), headers=headers)
    if response.status_code != 200:
        print("[ERROR]", "Unknown response.", "code:", response.status_code)
        return
    domain = response.json()
    if domain["valid"] == True:
        print("[INFO]", "Complete.")
    else:
        print("[WARNING]")
        pprint(domain["validation_results"])

def create_dns_record(args, dns_client, resource_group: str, zone_name: str, relative_record_set_name: str, record_type: str, params: dict):
    try:
        record = dns_client.record_sets.get(resource_group, zone_name, relative_record_set_name, record_type)
    except Exception as ex:
        print("[INFO]", ex)

        try:
            record = dns_client.record_sets.create_or_update(
                resource_group,
                zone_name,
                relative_record_set_name,
                record_type,
                params
            )
        except Exception as ex:
            print("[ERROR]", ex)
        else:
            print("[INFO]", "Create record success.")
            #print(record)
    else:
        print("[NOTICE]", "Exists record.")
        #print(record)

if __name__ == "__main__":
    main(args)
