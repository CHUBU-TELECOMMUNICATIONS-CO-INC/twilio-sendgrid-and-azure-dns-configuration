# twilio-sendgrid-and-azure-dns-configuration
Azure Cloud Shell上でTwilio sendgrid と Azure DNSを同時に設定するためのPythonスクリプト 

## Install
```bash
git clone https://github.com/CHUBU-TELECOMMUNICATIONS-CO-INC/twilio-sendgrid-and-azure-dns-configuration.git  
cd twilio-sendgrid-and-azure-dns-configuration  
pip3 install -r requirements.txt
cp .env.sample.txt .env  
vi .env  
python3 create_domain.py -a 192.168.1.1 example.com
```
