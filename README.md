# btt-stats-spi

## Requisites:
```bash
ufw allow 41337/tcp

sudo apt update

sudo apt install npm -y
sudo npm install pm2 -g
pm2 update

sudo apt install python3 python3-pip
python3 -m pip install bittensor --upgrade
source ~/.bashrc
```

## Installation / Deploy:
```bash
cd ~
git clone https://github.com/sirouk/btt-stats-api
cd ~/btt-stats-api

pm2 start http_server.py --name btt-stats-api --interpreter python3
```

# Fetch Subnets:
```bash
http://your.machine.ip.add:41337/subnet-list
```

# Fetch Metagraph (w/Filter):
```bash
http://your.machine.ip.add:41337/metagraph?netuid=1,3,5,7,9,21&egrep=TRUST&egrep=5G6F&egrep=5L7E&egrep=5C8J&egrep=5R7F
```
