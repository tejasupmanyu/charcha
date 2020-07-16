import requests
import json
import urllib
import os
import django
from django.core.management.base import BaseCommand, CommandError
from charcha.discussions.models import Tag

class Command(BaseCommand):
    help = 'Import deals from Hubspot, and save them as tags in database'

    def handle(self, *args, **options):
        hubspot_api_key = os.environ['HUBSPOT_API_KEY']
        hashedin, _ = Tag.objects.get_or_create(name="hashedin", parent=None, is_external=False)
        deals, _ = Tag.objects.get_or_create(name="deals", parent=hashedin, is_external=False)

        hubspot_deals = get_all_deals_from_hubspot(hubspot_api_key)

        for hubspot_deal in hubspot_deals:
            try:
                Tag.objects.update_or_create(
                    ext_id=hubspot_deal['ext_id'], 
                    parent=deals,
                    defaults=hubspot_deal
                )
            except django.db.utils.IntegrityError:
                # There are some duplicate names in hubspot
                # We append the ext_id to ensure names become unique
                unique_name = hubspot_deal['name'] + str(hubspot_deal['ext_id'])
                hubspot_deal['name'] = unique_name[:100]
                Tag.objects.update_or_create(
                    ext_id=hubspot_deal['ext_id'], 
                    parent=deals,
                    defaults=hubspot_deal
                )

def get_all_deals_from_hubspot(api_key):
    limit = 250
    deal_list = []
    get_all_deals_url = "https://api.hubapi.com/deals/v1/deal/paged?"
    parameter_dict = {'hapikey': api_key, 'limit': limit,
        'properties': ['pipeline', 'dealname', 'businessunit', 'dealstage', 'amount_in_home_currency'],
    }
    headers = {}

    # Paginate your request using offset
    has_more = True
    while has_more:
        r = requests.get(url= get_all_deals_url, params=parameter_dict, headers=headers)
        response_dict = json.loads(r.text)
        has_more = response_dict['hasMore']
        deal_list.extend(response_dict['deals'])
        parameter_dict['offset']= response_dict['offset']
        
    return _extract_deals(deal_list)

def _extract_deals(raw_deals):
    deals = []
    for raw_deal in raw_deals:
        deal = {}
        deal['is_external'] = True
        deal['ext_id'] = raw_deal['dealId']
        deal['ext_code'] = None
        deal['name'] = raw_deal.get('properties', {}).get('dealname', {}).get('value', None)
        deals.append(deal)

    return deals

if __name__ == '__main__':
    print(get_all_deals('1a75b241-c3ea-411e-9c7e-946e73e0f7a1'))
