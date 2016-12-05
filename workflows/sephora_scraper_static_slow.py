#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Retrieves product data from Sephora Rest API
import json
import logging
import math
import os
from urllib.parse import urlparse

import requests
from selenium import webdriver
from selenium.webdriver.common.by import By

from workflows.base_workflow import BaseWorkflow

logger = logging.getLogger(__name__)


class ProductScraper(BaseWorkflow):

    API_URL = 'http://www.sephora.com/rest'
    SITE_MAP_URL = 'http://www.sephora.com/sitemap/departments'
    PRODUCT_ENDPOINT = 'http://www.sephora.com/rest/products'
    PAGE_SIZE = 100

    def __init__(self):
        super(ProductScraper, self).__init__()
        self.product_path = os.path.join(self.data_path, 'products_new')
        self.categories = self.get_revised_categories()
        self.sku_scraper = SkuScraper(categories=self.categories)

    def process(self):
        self.save_products_data(self.categories)
        self.quit()

    def get_revised_categories(self):
        with open('/Users/mars_williams/kiss_and_makeup/revised_categories.json') as categories:
            cat = json.loads(categories.read())
            return {k: cat[k] for k in cat if cat[k]}

    def save_products_data(self, categories):
        for category in categories:
            try:
                seo_path = category.replace('.json', '')
                data = self.get_product_data(seo_path)
                data.update(self.add_products_sku_ids_and_category(
                    data.get('products', list()), categories[category]))
                self.save_product_data(data,
                                       category.replace(' ', '_'))
                self.sku_scraper.save_sku_data(products=data,
                                               category=category.replace(' ', '_'))

            except Exception as error:
                logger.error(error)

    def get_product_data(self, category):
        products_endpoint = '{API_URL}/products/' \
                            '?categoryName={category_name}' \
                            '&include_categories=true' \
                            '&includeAll' \
                            '&pageSize=' \
                            '{PAGE_SIZE}'.format(API_URL=self.API_URL,
                                                 category_name=category,
                                                 PAGE_SIZE=self.PAGE_SIZE)
        try:
            data = requests.get('{product_endpoint}&currentPage=1'.format(
                product_endpoint=products_endpoint))
            if data.content:
                data = data.json()
                total_products = data.get('total_products', 0)
                total_pages = math.ceil(total_products/self.PAGE_SIZE)
                for page in range(2, total_pages+1):
                    r = requests.get(
                        '{product_endpoint}&currentPage={page}'.format(
                            product_endpoint=products_endpoint,
                            page=page))
                    data['products'].extend(r.json().get('products', list()))
                return data
        except Exception as error:
            logger.error(error, products_endpoint)
            return {'product_endpoint': products_endpoint}

    def save_product_data(self, product_data, name):
        print('saving', name, 'product_data')
        with open(os.path.join(self.product_path,
                               name), 'w') as outfile:
            try:
                json.dump(product_data, outfile, sort_keys=True, indent=4)
            except json.decoder.JSONDecodeError:
                pass

    def add_products_sku_ids_and_category(self, data, category):
        enriched = list()
        for product in data:
            product_extra = product.copy()
            sku_ids, quick_look_desc = self.get_product_sku_ids(product['id'])
            product_extra['sku_ids'] = sku_ids
            product_extra['quick_look_desc'] = quick_look_desc
            product_extra['category'] = category
            enriched.append(product_extra)
        return {'products': enriched}

    def get_product_sku_ids(self, product_id):
        product_endpoint = '{PRODUCT_ENDPOINT}/' \
                           '{product_id}'.format(PRODUCT_ENDPOINT=self.PRODUCT_ENDPOINT,
                                                 product_id=product_id)
        try:
            data = requests.get(product_endpoint)
            if data.content:
                json_format = data.json()
                return json_format.get('sku_ids', str()).split(','),\
                       json_format.get('quick_look_desc', None)
        except Exception as error:
            logger.error(error, product_endpoint)
            return {'product_endpoint': product_endpoint}

    def quit(self):
        self.driver.quit()


class SkuScraper(BaseWorkflow):

    SKU_ENDPOINT = 'http://www.sephora.com/global/json/getSkuJson.jsp'

    def __init__(self, categories=None):
        super(SkuScraper, self).__init__()
        self.product_path = os.path.join(self.data_path, 'products_new')
        self.sku_path = os.path.join(self.data_path, 'skus_missed')
        self.error_path = os.path.join(self.data_path, 'errors')
        self.categories = categories

    def process(self):
        errors = self.get_error_data()
        self.save_sku_data(errors)

    def get_error_data(self):
        error_data = list()
        files = [os.path.join(self.error_path, file) for file in os.listdir(self.error_path)]
        for file_name in files:
            with open(file_name) as error:
                e = json.loads(error.read())
                error_data.append(e)
        return error_data

    def save_sku_data(self, errors):
        for error in errors:
            product_skus_data = self.get_product_skus_data(
                error['mapping'], error['category'])
            self.save_product_skus_data(
                product_skus_data,
                os.path.join(
                    self.sku_path,
                    error['category']))

    def get_product_skus_data(self, products, category):
        product_skus_data = dict()
        data = self.get_skus_data(products, category)
        product_skus_data.update(data)
        return product_skus_data

    def get_skus_data(self, products, category):
        skus_data = dict()
        product_sku_mapping = dict()
        for product in products:
            skus = ','.join((products[product]['sku_ids']))
            skus_endpoint = '{SKU_ENDPOINT}' \
                            '?skuId={sku_ids}' \
                            '&include_product' \
                            '=true'.format(SKU_ENDPOINT=self.SKU_ENDPOINT,
                                           sku_ids=skus)
            current_data = None
            try:
                data = requests.get(skus_endpoint)
                if data.content:
                    data = data.json()
                    current_data = data
                    if isinstance(data, list):
                        for sku in data:
                            sku_number = sku['sku_number']
                            print(sku_number, 'sku_number')
                            skus_data[sku_number] = sku
                            skus_data[sku_number]['variation_type'] = self.get_variation_type(sku,
                                                                                              products[product])
                            skus_data[sku_number]['quick_look_desc'] = products[product].get(
                                'quick_look_desc', None)
                            skus_data[sku_number]['category'] = products[product].get('category', None)
                    else:
                        sku_number = data['sku_number']
                        skus_data[sku_number] = data
                        skus_data[sku_number]['variation_type'] = self.get_variation_type(data,
                                                                                          products[product])
                        skus_data[sku_number]['quick_look_desc'] = products[product].get('quick_look_desc', None)
                        skus_data[sku_number]['category'] = products[product].get('category', None)
            except Exception as error:
                print(error, skus_endpoint)
                self.save_error({'skus_endpoint': skus_endpoint,
                                 'data': current_data if current_data else None,
                                 'mapping': product_sku_mapping,
                                 'category': category}, category)
        return skus_data

    def save_error(self, error, category):
        try:
            endpoint = error['skus_endpoint'].split(',')[1]
        except:
            endpoint = error['skus_endpoint'].split('skuId=')[1]
        with open('/Users/mars_williams/kiss_and_makeup/data/'
                  'errors/sku_mapping_{category}_{sku}.json'.format(category=category,
                                                                    sku=endpoint), 'w') as mapping_record:
            json.dump(error, mapping_record, sort_keys=True, indent=4)

    def get_variation_type(self, sku, product):
        if sku.get('primary_product', None) and sku['primary_product'].get('variation_type', None):
            return sku['primary_product']['variation_type']
        elif product.get('variation_type', None):
            return product['variation_type']
        else:
            return None

    def save_product_skus_data(self, data, name):
        print('saving', name, 'sku_data')
        with open(name, 'w') as outfile:
            try:
                json.dump(data, outfile, sort_keys=True, indent=4)
            except json.decoder.JSONDecodeError:
                logger.error(name)

SkuScraper().process()

