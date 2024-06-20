from pathlib import Path
import json
import pypd     # pip3 install pypd
import requests # pip3 install requests
import subprocess
import time
import toml     # pip3 install toml
import sys

import logging
from datetime import datetime, timezone, timedelta
import pytz

def timetz(*args):    return datetime.now(tz).timetuple()

logger = logging.getLogger()
tz = pytz.timezone('Asia/Seoul') # UTC, Asia/Seoul, Europe/Berlin
logging.Formatter.converter = timetz
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', datefmt = '%Y-%m-%d %H:%M:%S', level=logging.INFO)

def main():
  config = toml.load(Path('./config.toml').absolute())

  hostname = config['info']['hostname']
  sleep_sec = config['info']['sleep_sec']
  tg = config['info']['telegram']
  pd = config['info']['pagerduty']
  sl = config['info']['slack']

  daemons = ['indep_alarm']
  daemons += list(config['daemons'].keys())

  while True:
    for daemon in daemons:
      check_daemon(hostname, daemon, tg, pd, sl)

    time.sleep(sleep_sec)

def check_daemon(hostname, daemon_name, tg, pd, sl):
  try:
    daemon_status = subprocess.check_output(eval(f'f"""service {daemon_name} status | grep Active"""'), shell=True).decode('utf-8')
    daemon_status = daemon_status.split(":")[1].strip().split()[0]
  except subprocess.CalledProcessError as e:
    alarm_content = f"{daemon_name} is wrong in config.toml. Msg: {e}"
    send_tg_alarm(tg["bot_token"], tg["chatid_medium"], alarm_content)
    sys.exit(1)

  if daemon_status != "active":
    if daemon_name == "indep_alarm":
      subprocess.check_output(eval(f'f"""sudo systemctl start {daemon_name}"""'), shell=True)
      alarm_content = f"{daemon_name} has started : {hostname}"
      send_tg_alarm(tg["bot_token"], tg["chatid_info"], alarm_content)
    else :
      alarm_content = f"{daemon_name} is NOT active, check this node : {hostname}"
      # High - PagerDuty - Slack
      send_pd_alarm(pd["ep_ddo"], alarm_content)
      send_slack_alarm(sl["bot_token"], sl["channel_high"], alarm_content)

## Functions
def send_tg_alarm(token, chat_id, alarm_content):
  try:
    requestURL = f"https://api.telegram.org/bot{str(token)}/sendMessage?chat_id={chat_id}&text={str(alarm_content)}"
    requests.get(requestURL, timeout=5)
  except Exception as e:
    logger.error(f'Exception: {e}')

def send_pd_alarm(target_service, alarm_content):
  pypd.EventV2.create(data={
    'routing_key': target_service,
    'event_action': 'trigger',
    'payload': {
      'summary': alarm_content,
      'severity': 'critical',
      'source': 'indep_alarm',
    }
  })

def send_slack_alarm(token, channel, alarm_content):
  url = "https://slack.com/api/chat.postMessage"
  headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {token}"
  }
  payload = {
    "channel": channel,
    "text": alarm_content
  }

  response = requests.post(url, headers=headers, data=json.dumps(payload))

  if response.status_code != 200:
    raise Exception(f"Request to Slack API failed with status code {response.status_code}: {response.text}")

  response_data = response.json()
  if not response_data.get("ok"):
    raise Exception(f"Error from Slack API: {response_data.get('error')}")


if __name__ == "__main__":
  main()
