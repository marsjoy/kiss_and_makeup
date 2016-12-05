#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Retrieves product data from Sephora Rest API
import json
import logging
import os

from requests import Request, Session

from base_workflow import BaseWorkflow
from utilities.strings import remove_escape_characters, remove_html_tags

logger = logging.getLogger(__name__)


class SephoraLoader(BaseWorkflow):

    API_URL = 'https://makeup-production.herokuapp.com'
    SEPHORA_ENDPOINT = 'http://www.sephora.com'

    def __init__(self):
        super(SephoraLoader, self).__init__()
        self.sku_path = os.path.join(self.data_path, 'skus_missed')
        self.categories = dict()

    def process(self):
        json_files = [
            os.path.join(self.sku_path, filename)
            for filename in os.listdir(self.sku_path)]
        for json_file in json_files:
            print('reading json file', json_file)
            products_data = self.read_products_data(json_file)
            for product_data in products_data:
                transformed = self.transform_product_data(products_data[product_data])
                if transformed:
                    self.post_product_data(transformed)

    def read_products_data(self, json_file):
        with open(json_file) as j:
            return json.loads(j.read())

    def transform_product_data(self, data):
        if isinstance(data, dict):
            try:
                transformed_data = {
                    'brand': data.get('primary_product', dict()).get('brand_name', None),
                    'item': data.get('primary_product', dict()).get('display_name', None),
                    'shade': self.get_shade(data),
                    'category': data['category'],
                    'specs': self.get_specs(data),
                    'skus': {
                        'sephora': data['sku_number']
                    },
                    'size': self.get_sku_size(data.get('sku_size', None)),
                    'products': list(),
                    'images': self.get_images(data),
                }
                return transformed_data
            except Exception as error:
                print(error)

    def get_sku_size(self, data):
        if data:
            split = data.split('/')[0].split()
            if 'Closed:' in split:
                return {'value': None,
                        'unit': None}
            if 'x' in split:
                if split[1] == 'x':
                    try:
                        value = float(split[0]) * float(split[2])
                    except ValueError:
                        value = None
                    try:
                        unit = split[3]
                    except IndexError:
                        unit = None
                    return {'value': value,
                            'unit': unit}
                elif split[2] == 'x':
                    try:
                        value = float(split[0]) * float(split[3])
                    except ValueError:
                        value = None
                    try:
                        unit = split[1]
                    except IndexError:
                        unit = None
                    return {'value': value,
                            'unit': unit}
            try:
                value = float(split[0].strip())
            except ValueError:
                value = None
            try:
                unit = ' '.join(split[1:])
            except IndexError:
                unit = None
            return {'value': value,
                    'unit': unit}
        else:
            return {'value': None,
                    'unit': None}

    def get_shade(self, data):
        variation = data['variation_value']
        if data.get('variation_type', None).lower() == 'color':
            return variation
        else:
            return ''

    def get_specs(self, data):
        ingredients = remove_escape_characters(
            remove_html_tags(data.get('ingredients', None), 'html.parser'))
        summary = remove_escape_characters(
            remove_html_tags(data.get('quick_look_desc', None), 'html.parser'))
        description = remove_escape_characters(
            remove_html_tags(data.get('additional_sku_desc', None), 'html.parser'))
        specs = {'ingredients': ingredients} if ingredients else {}
        specs.update({'summary': summary} if summary else {})
        specs.update({'description': description} if description else {})
        return specs

    def get_images(self, data):
        images = [
            {
                'url': self.get_sephora_endpoint(data.get('swatch_image', '')),
                'type': 'swatch',
                'size': 'small'
            }]
        images.extend([{
                           'url': self.get_sephora_endpoint(grid_image),
                           'type': 'product',
                           'size': 'medium'
                       } for grid_image in data.get('grid_images', '').split()
                       if 'main' in grid_image.lower()])
        images.extend([{
                           'url': self.get_sephora_endpoint(thumb_image),
                           'type': 'product',
                           'size': 'small'
                       } for thumb_image in data.get('thumb_images', '').split()
                       if 'main' in thumb_image.lower()])
        images.extend([{
                           'url': self.get_sephora_endpoint(large_image),
                           'type': 'product',
                           'size': 'xlarge'
                       } for large_image in data.get('large_images', '').split()
                       if 'main' in large_image.lower()])
        images.extend([{
                           'url': self.get_sephora_endpoint(hero_image),
                           'type': 'product',
                           'size': 'large'
                       } for hero_image in data.get('hero_images', '').split()
                       if 'main' in hero_image.lower()])
        return images

    def get_sephora_endpoint(self, path):
        if path:
            return '{SEPHORA_ENDPOINT}' \
                   '{path}'.format(SEPHORA_ENDPOINT=self.SEPHORA_ENDPOINT,
                                   path=path)
        else:
            return None

    def post_product_data(self, product):
        products_endpoint = '{API_URL}/products/'.format(API_URL=self.API_URL)
        try:
            request = Request(method='POST',
                              url=products_endpoint,
                              json=product,
                              auth=(self.config['heroku']['username'],
                                    self.config['heroku']['password']))
            session = Session()
            response = session.send(request.prepare())
            print(response.status_code)
            if response.status_code != 201:
                if response.status_code != 409:
                    print(response.request.body, response.status_code)
        except Exception:
            pass

SephoraLoader().process()
