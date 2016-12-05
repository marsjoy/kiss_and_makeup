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

    def __init__(self, use_firefox=False):
        super(ProductScraper, self).__init__()
        self.use_firefox = use_firefox
        self.phantomjs_path = '/usr/local/lib/node_modules/' \
                              'phantomjs/lib/phantom/bin/phantomjs'
        self.product_path = os.path.join(self.data_path, 'products')
        self.driver = None
        self.categories = self.get_revised_categories()
        self.sku_scraper = SkuScraper(categories=self.categories)

    def set_driver(self, root_url):
        if not self.use_firefox:
            driver = webdriver.PhantomJS(executable_path=self.phantomjs_path)
        else:
            driver = webdriver.Firefox()
        driver.set_window_size(480, 320)
        driver.get(root_url)
        self.driver = driver

    def process(self):
        self.save_products_data(self.categories)
        self.quit()

    def get_revised_categories(self):
        with open('/Users/mars_williams/kiss_and_makeup/revised_categories.json') as categories:
            cat = json.loads(categories.read())
            return {k: cat[k] for k in cat if cat[k]}

    def get_dynamic_categories(self):
        categories = list()
        main_category_items = self.driver.find_element(
            By.CSS_SELECTOR,
            '.Sitemap').find_elements(By.CSS_SELECTOR,
                                      '.Sitemap-item')
        for category_item in main_category_items:
            category_item_object = category_item.find_element(
                By.TAG_NAME,
                'h2')
            category_seo_path = urlparse(category_item_object.find_element(
                By.TAG_NAME,
                'a').get_attribute('href')).path
            category_name = category_item_object.find_element(
                By.TAG_NAME,
                'a').text.lower()
            categories.append({
                'name': category_name,
                'seo_path': category_seo_path})
        return categories

    def get_site_map(self):
        self.set_driver(self.SITE_MAP_URL)

    def save_dynamic_products_data(self, categories):
        for category in categories:
            if category.get('seo_path', None):
                try:
                    data = self.get_product_data(
                        category['seo_path'][1:])
                    data.update(self.add_products_sku_ids(
                        data.get('products', list())))
                    self.save_product_data(data,
                                           category['seo_path'][1:])
                    sub_categories = data['categories'].get(
                        'sub_categories', list())
                    for sub_category in sub_categories:
                        if sub_category.get('seo_path', None):
                            data = self.get_product_data(
                                sub_category['seo_path'][1:])
                            data.update(self.add_products_sku_ids(
                                data.get('products', list())))
                            self.save_product_data(data,
                                                   sub_category['seo_path'][1:])
                            subs = sub_category.get('sub_categories', list())
                            for sub in subs:
                                if sub.get('seo_path', None):
                                    data = self.get_product_data(
                                        sub['seo_path'][1:])
                                    data.update(self.add_products_sku_ids(
                                        data.get('products', list())))
                                    self.save_product_data(data,
                                                           sub['seo_path'][1:])
                                else:
                                    logger.error(category)
                        else:
                            logger.error(category)
                except Exception as error:
                    logger.error(error)
            else:
                logger.error(category)

    def save_products_data(self, categories):
        for category in categories:
            try:
                print(category, 'CATEGORY')
                seo_path = category.replace('.json', '')
                data = self.get_product_data(seo_path)
                data.update(self.add_products_sku_ids(
                    data.get('products', list())))
                self.save_product_data(data,
                                       categories[category])
                self.sku_scraper.save_sku_data(products=data,
                                               category=categories[category])

            except Exception as error:
                logger.error(error)

    def save_dynamic_products_data(self, categories):
        for category in categories:
            if category.get('seo_path', None):
                try:
                    data = self.get_product_data(
                        category['seo_path'][1:])
                    data.update(self.add_products_sku_ids(
                        data.get('products', list())))
                    self.save_product_data(data,
                                           category['seo_path'][1:])

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
        print(products_endpoint)
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
        print('saving', name)
        with open(os.path.join(self.product_path,
                               '{name}.json'.format(name=name)), 'w') as outfile:
            try:
                json.dump(product_data, outfile, sort_keys=True, indent=4)
            except json.decoder.JSONDecodeError:
                pass

    def add_products_sku_ids(self, data):
        enriched = list()
        for product in data:
            product_extra = product.copy()
            sku_ids, quick_look_desc = self.get_product_sku_ids(product['id'])
            product_extra['sku_ids'] = sku_ids
            product_extra['quick_look_desc'] = quick_look_desc
            enriched.append(product_extra)
        return {'products': enriched}

    def get_product_sku_ids(self, product_id):
        product_endpoint = '{PRODUCT_ENDPOINT}/' \
                           '{product_id}'.format(PRODUCT_ENDPOINT=self.PRODUCT_ENDPOINT,
                                                 product_id=product_id)
        print(product_endpoint)
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
        self.product_path = os.path.join(self.data_path, 'products')
        self.sku_path = os.path.join(self.data_path, 'skus')
        self.categories = categories

    def process(self):
        self.save_sku_data()

    def old_save_sku_data(self):
        json_files = {
            os.path.join(self.product_path, category): self.categories[category]
            for category in self.categories}
        for category in json_files:
            with open(category) as j:
                products = json.loads(j.read())
                product_skus_data = self.get_product_skus_data(
                    products['products'])
                self.save_product_skus_data(
                    product_skus_data,
                    os.path.join(
                        self.sku_path,
                        '{revised_category}.json'.format(
                            revised_category=json_files[category].replace(' ', '_'))))

    def save_sku_data(self, products, category):
        product_skus_data = self.get_product_skus_data(
            products['products'])
        self.save_product_skus_data(
            product_skus_data,
            os.path.join(
                self.sku_path,
                '{revised_category}.json'.format(
                    revised_category=category.replace(' ', '_'))))

    def get_product_skus_data(self, products):
        product_skus_data = dict()
        data = self.get_skus_data(products)
        product_skus_data.update(data)
        return product_skus_data

    def get_skus_data(self, products):
        skus_data = dict()
        product_sku_mapping = dict()
        skus = []
        for product in products:
            product_sku_mapping.update({sku: product for sku in product['sku_ids']})
            skus.extend(product['sku_ids'])
        print(product_sku_mapping, 'mapping')
        skus_endpoint = '{SKU_ENDPOINT}' \
                        '?skuId={sku_ids}' \
                        '&include_product' \
                        '=true'.format(SKU_ENDPOINT=self.SKU_ENDPOINT,
                                       sku_ids=','.join(skus))
        try:
            data = requests.get(skus_endpoint)
            if data.content:
                data = data.json()
                if isinstance(data, list):
                    for sku in data:
                        sku_number = sku['sku_number']
                        skus_data[sku_number] = sku
                        skus_data[sku_number]['variation_type'] = self.get_variation_type(sku,
                                                                                          product_sku_mapping[sku_number])
                        skus_data[sku_number]['quick_look_desc'] = product_sku_mapping[sku_number].get(
                            'quick_look_desc', None)
                else:
                    sku_number = data['sku_number']
                    skus_data[sku_number] = data
                    skus_data[sku_number]['variation_type'] = self.get_variation_type(data,
                                                                                      product_sku_mapping[sku_number])
                    skus_data[sku_number]['quick_look_desc'] = product_sku_mapping[sku_number].get('quick_look_desc', None)
        except Exception as error:
            logger.error(error, skus_endpoint)
            return {'skus_endpoint': skus_endpoint}
        return skus_data

    def get_variation_type(self, sku, product):
        if sku.get('primary_product', None) and sku['primary_product'].get('variation_type', None):
            return sku['primary_product']['variation_type']
        elif product.get('variation_type', None):
            return product['variation_type']
        else:
            return None

    def save_product_skus_data(self, data, name):
        with open(name, 'w') as outfile:
            try:
                json.dump(data, outfile, sort_keys=True, indent=4)
            except json.decoder.JSONDecodeError:
                logger.error(name)

ProductScraper().process()
# SkuScraper().process()
