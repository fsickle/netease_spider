# -*- coding: utf-8 -*-
from scrapy import Spider, Request, FormRequest
from netease_spider.items import NeteaseSpiderItem
import json
import os
import base64
import codecs
from Crypto.Cipher import AES
import re
import time
import random

# 维持一个全局变量，用于存储已经爬取过的歌单，避免太多的重复爬取
music_sheet = list()


class SpiderSpider(Spider):
    name = 'spider'
    allowed_domains = ['music.163.com']
    start_urls = ['http://music.163.com/']
    second_data = '010001'
    third_data = '00e0b509f6259df8642dbc35662901477df22677ec152b5ff68ace615bb7b725152b3ab17a876aea8a5aa76d2e417629' \
                 'ec4ee341f56135fccf695280104e0312ecbda92557c93870114af6c9d05c4f7f0c3685b7a46bee255932575cce10b424' \
                 'd813cfe4875d3e82047b97ddef52741d546b8e289dc6935b3ece0462db0a22b8e7'
    fourth_data = '0CoJUm6Qyw8W8jud'
    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/68.0.344'
                      '0.75Safari/537.36',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Referer': 'https://music.163.com/',
        'Host': 'music.163.com'
    }

    # 选取一些多样化的歌曲，作为最开始的爬取对象
    def start_requests(self):
        urls = ['https://music.163.com/song?id=442016694', 'https://music.163.com/song?id=30482293',
                'https://music.163.com/song?id=447926071', 'https://music.163.com/song?id=22722555',
                'https://music.163.com/song?id=557513151', 'https://music.163.com/song?id=451703096']
        headers = self.headers.copy()
        for url in urls:
            yield Request(url, headers=headers, callback=self.get_comment)

    #获得歌曲的名称，以及它所关联的歌单，对其评论url发起请求，以及请求歌单url
    def get_comment(self, response):
        url = response.url
        name = re.search('"title": "(.*?)",', response.text).group(1)
        music_id = re.search('id=(.*)', url).group(1)
        comment_url = "https://music.163.com/weapi/v1/resource/comments/R_SO_4_" + music_id + "?csrf_token="
        headers = self.headers.copy()
        first_data = self.get_first_data(url)
        data = self.encrypted_request(first_data, self.second_data, self.third_data, self.fourth_data)
        yield FormRequest(comment_url, headers=headers, formdata=data, callback=self.parse_comment, meta={'name': name})

        list_url = response.css('div.g-bd4.f-cb div.g-sd4 div ul.m-rctlist.f-cb li div.info p.f-thide a::a'
                                'ttr("href")').extract()
        for i in list_url:
            sheet_url = 'https://music.163.com' + i
            global music_sheet
            if sheet_url not in music_sheet:
                music_sheet.append(sheet_url)
                yield Request(sheet_url, headers=headers, callback=self.parse_sheet, meta={'url': url})
            else:
                print('歌单%s,已经爬取过' % sheet_url)

    # 凡茜评论的json，并将其存储到mongodb
    def parse_comment(self, response):
        comments = json.loads(response.text)
        item = NeteaseSpiderItem()
        length = len(comments["hotComments"])
        if length > 0:
            comment = list()
            for i in range(length):
                comment.append(comments["hotComments"][i]["content"])
            item['comment'] = comment
            total = comments["total"]
            item["total"] = str(total)
            item_url = response.url
            item['url'] = item_url
            item['name'] = response.meta['name']
            # print(result)
            yield item
        else:
            item['comment'] = 'no comment'
            total = comments["total"]
            item["total"] = str(total)
            item_url = response.url
            item['url'] = item_url
            item['name'] = response.meta['name']
            # print(result)
            yield item

    #对歌单进行解析，得到其中的歌曲 url，再调用求取评论的函数
    def parse_sheet(self, response):
        headers = self.headers.copy()
        urls = list()
        song_urls = response.css('div#song-list-pre-cache ul.f-hide li a::attr("href")').extract()
        # print(song_urls)
        for i in song_urls:
            url = 'https://music.163.com' + i
            urls.append(url)
        # print(urls)
        from_url = response.meta['url']
        # print(from_url)
        if from_url in urls:
            urls.remove(str(from_url))
        # print(url_list)
        for url in urls:
            yield Request(url, headers=headers, callback=self.get_comment)

    #以下是网易云音乐的params加密
    def createSecretKey(self, size):
        '''获取随机十六个字母拼成的字符串'''
        '''
        os.urandom(n):产生n个字节的字符串
        ord(n):返回对应的十进制整数
        hex():将十进制整数转换成16进制，以字符串表示
        '''
        return (''.join(map(lambda x: (hex(ord(x))[2:]), str(os.urandom(size)))))[0:16]

    def aesEncrypt(self, text, secKey):
        '''encText加密方法:AES'''
        '''
        chr():以整数做参数，返回字符
        '''
        pad = 16 - len(text) % 16
        if isinstance(text, bytes):
            text = text.decode('utf-8')
        text = text + str(pad * chr(pad))
        encryptor = AES.new(secKey, AES.MODE_CBC, '0102030405060708')
        ciphertext = encryptor.encrypt(text)
        ciphertext = base64.b64encode(ciphertext)
        return ciphertext

    def rsaEncrypt(self, secKey, pubKey, modulus):
        '''encSecKey的加密方法:rsa'''
        text = secKey[::-1]
        rs = int(codecs.encode(text.encode('utf-8'), 'hex_codec'), 16) ** int(pubKey, 16) % int(modulus, 16)
        return format(rs, 'x').zfill(256)

    def encrypted_request(self, text, pubKey, modulus, nonce):
        text = json.dumps(text)
        secKey = self.createSecretKey(16)
        encText = self.aesEncrypt(self.aesEncrypt(text, nonce), secKey)
        encSecKey = self.rsaEncrypt(secKey, pubKey, modulus)
        data = {
            'params': encText,
            'encSecKey': encSecKey,
        }
        return data

    def get_first_data(self, url):
        '''根据url获取不同的id，构造第一个参数'''
        music_id = re.search('id=(.*)', url).group(1)
        rid = "R_SO_4_" + music_id
        first_data = {"rid": rid, "offset": "0", "total": "true", "limit": "20", "csrf_token": ""}
        # print(first_data)
        return first_data

