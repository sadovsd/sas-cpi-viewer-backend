import os
from dotenv import load_dotenv

load_dotenv()

SAS_config_names=['oda']

oda = {'java' : '/usr/bin/java',
#My SAS onDemand 'US Home Region 2'
'iomhost' : ['odaws01-usw2-2.oda.sas.com','odaws02-usw2-2.oda.sas.com'],
'iomport' : 8591,
# 'authkey' : 'oda',
'omruser': os.getenv('OMRUSER'),
'omrpw': os.getenv('OMRPW'),
'encoding' : 'utf-8'
}