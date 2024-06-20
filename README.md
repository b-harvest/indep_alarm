# indep_alarm

cosmos-sdk based alert program inside node with free disk check, height stuck

## TL; DR

```bash
git clone https://github.com/b-harvest/indep_alarm.git ddo_scripts
cd ddo_scripts

sudo apt-get -y install python3-pip
sudo -H pip3 install -r requirements.txt

# fill up your configuration
mv config.toml.example config.toml

## Create service files and start
bash indep_alarm_service.sh

sudo systemctl daemon-reload

sudo systemctl start indep_alarm
sudo systemctl status indep_alarm

sudo systemctl start indep_alarm_check
sudo systemctl status indep_alarm_check
```
