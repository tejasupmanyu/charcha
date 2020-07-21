import requests
import json
import urllib
import os
import django
from django.core.management.base import BaseCommand, CommandError
from charcha.discussions.models import Tag
from django.utils import timezone

# For a list of all properties of a deal, see 
# https://api.hubapi.com/properties/v2/deals/properties?hapikey={{token}}
HUBSPOT_PROPERTIES = ['hubspot_owner_id', 'dealname', 'businessunit', 'dealstage', 'description', 'source', 'geography']

# These are the stages we expect
# At runtime, we verify the stages have not changed
EXPECTED_DEAL_STAGES = {
    'appointmentscheduled': '1-Qualification', 
    'qualifiedtobuy': '2-Presales', 
    'presentationscheduled': '3-Waiting Evaluation', 
    'decisionmakerboughtin': '4-Negotiation',
    'contractsent': '5-SOW Pending', 
    'closedwon': '6-Closed Won', 
    'closedlost': '7-Closed Lost', 
    '389da328-069b-4414-97f2-63278e4a95ce': '8-Abandoned', 
}

# We only want to show deals upto 5-SOW Pending in Charcha UI
# The others will be marked is_visible=False
VISIBLE_STAGES = {"appointmentscheduled", "qualifiedtobuy", 
        "presentationscheduled", "decisionmakerboughtin", "contractsent"}

# We rename deal properties for our database
TAG_PROPERTIES = {
    'hubspot_owner_id': 'deal_owner',
    'businessunit': "business_unit",
    'dealstage': "deal_stage"
}
class Command(BaseCommand):
    help = 'Import deals from Hubspot, and save them as tags in database'

    def handle(self, *args, **options):
        hubspot_api_key = os.environ['HUBSPOT_API_KEY']
        hashedin, _ = Tag.objects.get_or_create(name="Hashedin", parent=None, is_external=False)
        sales, _ = Tag.objects.get_or_create(name="Sales", parent=hashedin, is_external=False)
        proposal, _ = Tag.objects.get_or_create(name="Proposals", parent=sales, is_external=False)
        
        hubspot_deals = get_all_deals_from_hubspot(hubspot_api_key)
        for hubspot_deal in hubspot_deals:
            try:
                Tag.objects.update_or_create(
                    ext_id=hubspot_deal['ext_id'], 
                    parent=proposal,
                    defaults=hubspot_deal
                )
            except django.db.utils.IntegrityError:
                # There are some duplicate names in hubspot
                # We append the ext_id to ensure names become unique
                unique_name = hubspot_deal['name'] + str(hubspot_deal['ext_id'])
                hubspot_deal['name'] = unique_name[:100]
                Tag.objects.update_or_create(
                    ext_id=hubspot_deal['ext_id'], 
                    parent=proposal,
                    defaults=hubspot_deal
                )

def get_deal_stages(api_key):
    parameter_dict = {'hapikey': api_key, 'limit': 250}
    url = "https://api.hubapi.com/crm-pipelines/v1/pipelines/deals"
    r = requests.get(url=url, params=parameter_dict)
    stages = {}
    for raw_stage in r.json()['results'][0]['stages']:
        label = raw_stage['label']
        stageId = raw_stage['stageId']
        stages[stageId] = label

    return stages

def get_hubspot_users(api_key):
    parameter_dict = {'hapikey': api_key, 'limit': 250}
    url = "https://api.hubapi.com/owners/v2/owners"
    r = requests.get(url=url, params=parameter_dict)
    users = {}
    for raw_user in r.json():
        id = raw_user['ownerId']
        email = raw_user['email']
        users[str(id)] = email
    return users

def get_all_deals_from_hubspot(api_key):
    limit = 250
    deal_list = []
    get_all_deals_url = "https://api.hubapi.com/deals/v1/deal/paged?"
    parameter_dict = {'hapikey': api_key, 'limit': limit,
        'properties': HUBSPOT_PROPERTIES,
    }
    # Paginate your request using offset
    has_more = True
    while has_more:
        r = requests.get(url= get_all_deals_url, params=parameter_dict)
        response_dict = json.loads(r.text)
        has_more = response_dict['hasMore']
        deal_list.extend(response_dict['deals'])
        parameter_dict['offset']= response_dict['offset']

    users = get_hubspot_users(api_key)
    deal_stages = get_deal_stages(api_key)
    if deal_stages != EXPECTED_DEAL_STAGES:
        raise Exception("Expected deal stages not the same as the actual deal stages. To fix, update EXPECTED_DEAL_STAGES")

    return _extract_deals(deal_list, users, deal_stages)
    
def _extract_deals(raw_deals, users, deal_stages):
    deals = []
    for raw_deal in raw_deals:
        portalId = raw_deal['portalId']
        dealId = raw_deal['dealId']
        deal = {}
        deal['is_external'] = True
        deal['ext_id'] = dealId
        deal['name'] = _get_nested(raw_deal, "properties.dealname.value")
        deal['fqn'] = "Proposals: " + deal['name']
        deal['is_visible'] = is_deal_visible(raw_deal)
        deal['ext_link'] = "https://app.hubspot.com/contacts/" + str(portalId) + "/deal/" + str(dealId)
        deal['imported_on'] = timezone.now()
        attributes = {}
        for key in HUBSPOT_PROPERTIES:
            # We have already extracted dealname above, so skip it
            if key == 'dealname':
                continue
            value = _get_nested(raw_deal, "properties." + key + ".value")
            if value:
                value = str(value)

            if key == 'hubspot_owner_id':
                value = users.get(value, value)
            elif key == 'dealstage':
                value = deal_stages.get(value, value)

            # Rename the key to make sense for our database
            key = TAG_PROPERTIES.get(key, key)
            attributes[key] = value
            
        deal['attributes'] = attributes
        deals.append(deal)

    return deals

def is_deal_visible(deal):
    deal_stage = _get_nested(deal, "properties.dealstage.value")
    if deal_stage in VISIBLE_STAGES:
        return True
    else:
        return False

def _get_nested(obj, path):
    tokens = path.split('.')
    for key in tokens:
        obj = obj.get(key, None)
        if not obj:
            return None
    return obj