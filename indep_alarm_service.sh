cd /home/ubuntu/ddo_scripts;echo "[Unit]
Description=indep_alarm
After=network-online.target
[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/ddo_scripts
ExecStart=/usr/bin/python3 /home/ubuntu/ddo_scripts/indep_alarm.py
SyslogIdentifier=indep_alarm
Restart=always
RestartSec=200
LimitNOFILE=4096
[Install]
WantedBy=multi-user.target" > indep_alarm.service;sudo mv indep_alarm.service /etc/systemd/system/;sudo systemctl enable indep_alarm.service

cd /home/ubuntu/ddo_scripts;echo "[Unit]
Description=indep_alarm_check
After=network-online.target
[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/ddo_scripts
ExecStart=/usr/bin/python3 /home/ubuntu/ddo_scripts/indep_alarm_check.py
SyslogIdentifier=indep_alarm_check
Restart=always
RestartSec=200
LimitNOFILE=4096
[Install]
WantedBy=multi-user.target" > indep_alarm_check.service;sudo mv indep_alarm_check.service /etc/systemd/system/;sudo systemctl enable indep_alarm_check.service