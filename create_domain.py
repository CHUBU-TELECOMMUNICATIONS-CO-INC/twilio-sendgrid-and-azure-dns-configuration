#!/usr/bin/env python3

import argparse
import json
import os
import re
import validators
from pprint import pprint

import requests
import urllib3
from dotenv import load_dotenv
from azure.cli.core import get_default_cli

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

args = parser.parse_args()

def main(args: dict):
    result_validation = validators.domain(args.domain_name)
    if args.domain_name is None or result_validation != True:
        print("[ERROR]", "Incorrect domain name.")
        return
    
    subscription_id = os.getenv("SUBSCRIPTION_ID", None)
    if subscription_id is None:
        print("[ERROR]", "Invalid Subscription id.")
        return

    cli = get_default_cli()
    response = cli.invoke(
        [
            "login",
            "--identity",
            "--output",
            "none"
        ]
    )

    if response != 0:
        print("[ERROR]", "Azure login failed.")
        return
        
    response = cli.invoke(
        [
            "account",
            "set",
            "--subscription",
            subscription_id,
            "--output",
            "none"
        ]
    )

    if response != 0:
        print("[ERROR]", "Azure set subscription failed.")
        return

    execute(args, cli)

    response = cli.invoke(
        [
            "logout",
            "--output",
            "none"
        ]
    )

def execute(args: dict, cli):
    domain_name: str = args.domain_name
    zone_name: str = None
    match = re.search(r"^.*?\.?([^\.]+\.[a-z]+)$", domain_name)
    if match:
        zone_name = match.group(1)
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
    
    cli = get_default_cli()
    response = cli.invoke(
        [
            "network",
            "dns",
            "record-set",
            "a",
            "show",
            "--resource-group",
            resource_group,
            "--name",
            zone_name,
            "--zone-name",
            domain_name,
            "--only-show-errors",
            "--output",
            "json"
        ]
    )

    response = requests.get("https://api.sendgrid.com/v3/whitelabel/domains/{:d}".format(domain_id), headers=headers)
    if response.status_code != 200:
        print("[ERROR]", "Unknown response.", "code:", response.status_code)
        return
    #pprint(response.json())

if __name__ == "__main__":
    main(args)
