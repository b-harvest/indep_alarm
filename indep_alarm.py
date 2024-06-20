import json
import shutil
import time
from datetime import datetime

import requests # pip3 install requests
import toml     # pip3 install tomli
import pypd     # pip3 install pypd

from pathlib import Path

from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from requests import Session

import logging
from datetime import datetime, timezone, timedelta
import pytz

def timetz(*args):    return datetime.now(tz).timetuple()

logger = logging.getLogger()
tz = pytz.timezone('Asia/Seoul') # UTC, Asia/Seoul, Europe/Berlin
logging.Formatter.converter = timetz
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', datefmt = '%Y-%m-%d %H:%M:%S', level=logging.INFO)

retries = Retry(total=10, connect=8, read=2, backoff_factor=0.2, status_forcelist=[500, 502, 503, 504, 429])

def main():

  config = toml.load(Path('./config.toml').absolute())

  hostname = config['info']['hostname']
  sleep_sec = config['info']['sleep_sec']
  free_disk_threshold_root = config['info']['root_disk_trigger']
  free_disk_threshold_data = config['info']['data_disk_trigger']
  tg = config['info']['telegram']
  pd = config['info']['pagerduty']
  sl = config['info']['slack']

  node_list = []

  for (daemon, info) in config['daemons'].items():
    node_list.append(NodeInfo(hostname, daemon, info['rpc'], info['validator_hex_address'], info['missing_trigger'], sleep_sec, tg, pd, sl))
  for (daemon, info) in config['daemons'].items():
    node_list.append(NodeInfo(hostname, daemon, info['rpc'], info['validator_hex_address'], info['missing_trigger'], sleep_sec, tg, pd, sl))

  while True:

    # Disk Free Check
    check_freedisk("/", hostname, free_disk_threshold_root, pd, sl)
    check_freedisk("/data", hostname, free_disk_threshold_data, pd, sl)

    # Last Height Check
    for node in node_list:
      node.get_last_height()

    # ***** Wait *****
    time.sleep(sleep_sec)

    # Check : stuck, block missing
    for node in node_list:
      if node.get_current_height():
        node.check_height_stuck(sleep_sec)
        node.check_block_missing()
        node.update_last_height()


class NodeInfo:

  def __init__(self, hostname, chain_name, rpc_url, validator_hex_address, block_missing_threshold, sleep_sec, tg, pd, sl):
    self.last_height = 0
    self.current_height = 0
    self.hostname = hostname
    self.chain_name = chain_name
    self.rpc_url = rpc_url
    self.validator_hex_address = validator_hex_address
    self.block_missing_threshold = block_missing_threshold
    self.sleep_sec = sleep_sec
    self.tg = tg
    self.pd = pd
    self.sl = sl

  def get_last_height(self):
    with Session() as sess:
      try:
        sess.mount('http://',  HTTPAdapter(max_retries=retries))
        sess.mount('https://', HTTPAdapter(max_retries=retries))
        status = json.loads(sess.get(self.rpc_url + "/status").text)
        last_height = int(status["result"]["sync_info"]["latest_block_height"])
        self.last_height = last_height
      except Exception as e:
        alarm_content = f'{self.hostname} : {self.chain_name} - get_last_height - Exception: {e}'
        # Low - Telegram
        send_tg_alarm(self.tg["token"], self.tg["chatid_low"], alarm_content)

  def get_current_height(self):
    with Session() as sess:
      try:
        sess.mount('http://',  HTTPAdapter(max_retries=retries))
        sess.mount('https://', HTTPAdapter(max_retries=retries))
        status = json.loads(sess.get(self.rpc_url + "/status").text)
        current_height = int(status["result"]["sync_info"]["latest_block_height"])
        self.current_height = current_height
        return True

      except Exception as e:
        alarm_content = f'{self.hostname} : {self.chain_name} - get_current_height - Exception: {e}'
        # Low - Telegram
        send_tg_alarm(self.tg["bot_token"], self.tg["chatid_low"], alarm_content)

  def update_last_height(self):
    self.last_height = self.current_height

  def check_height_stuck(self, sleep_sec):
    current_datetime = datetime.now()
    try:
      blocktime = float(sleep_sec/(self.current_height-self.last_height))
    except:
      blocktime = 0.0
    if self.current_height != self.last_height:
      blocktime = self.sleep_sec/(self.current_height-self.last_height)

    log_entry = f'{current_datetime} Last: {self.last_height}, Current: {self.current_height}, Diff: {self.current_height-self.last_height}, BlockTime: {blocktime}'
    with open('/tmp/indep.log', 'a') as log_file:
      log_file.write(log_entry + '\n')

    if self.last_height == self.current_height :
      alarm_content = f"{self.hostname} - {self.chain_name} : height stucked!"
      # High - PagerDuty - Slack
      target_ep = self.pd["target_ep"]
      send_pd_alarm(self.pd[target_ep], alarm_content)
      send_slack_alarm(self.sl["bot_token"], self.sl["channel_high"], alarm_content)

  def check_block_missing(self):
    if self.validator_hex_address == "":
      return

    missing_block_cnt = 0
    for height in range(self.last_height+1, self.current_height+1):
      precommit_match = False
      precommits = json.loads(requests.get(self.rpc_url + "/commit?height=" + str(height), timeout=5).text)["result"]["signed_header"]["commit"]["signatures"]

      for precommit in precommits:
        try:
          validator_address = precommit["validator_address"]
        except:
          validator_address = ""
        if validator_address == self.validator_hex_address:
          precommit_match = True
          break

      if precommit_match == False:
        missing_block_cnt += 1

    if missing_block_cnt >= self.block_missing_threshold:
      current_datetime = datetime.now()
      log_entry = f"{current_datetime} Missed: {missing_block_cnt},  Threshold: {self.block_missing_threshold}"
      with open('/tmp/indep.log', 'a') as log_file:
        log_file.write(log_entry + '\n')

      alarm_content = f'{self.hostname} - {self.chain_name} : missing block count({missing_block_cnt}) >=  threshold({self.block_missing_threshold})'
      # High - PagerDuty - Slack
      target_ep = self.pd["target_ep"]
      send_pd_alarm(self.pd[target_ep], alarm_content)
      send_slack_alarm(self.sl["bot_token"], self.sl["channel_high"], alarm_content)


## Functions
def check_freedisk(disk_location, hostname, free_disk_threshold, pd, sl):
  total, used, free = shutil.disk_usage(disk_location)

  if (free//(2**30)) < free_disk_threshold:
    alarm_content = f'{hostname} : free disk of {disk_location} is less than {free_disk_threshold} GB'
    # High - PagerDuty - Slack
    send_pd_alarm(pd["ep_ddo"], alarm_content)
    send_slack_alarm(sl["bot_token"], sl["channel_high"], alarm_content)

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