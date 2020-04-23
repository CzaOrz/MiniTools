import re
import logging
import requests
import datetime
from copy import deepcopy
from minitools.scrapy import miniSpider, next_page_request
from scrapy import Request, FormRequest
from minitools import *


def img2base64(img):
    if isinstance(img, str) and img.startswith("http"):
        img = requests.get(img).content
    if isinstance(img, bytes):
        img = base64img.byte2base64(img)
    if not isinstance(img, str):
        raise Exception("��֧�� {} ��ʽ��ͼƬ".format(type(img)))
    return "data:image/png;base64," + img


def captcha(img):
    if isinstance(img, bytes):
        img = base64img.byte2base64(img)
    return img


class MySpider(miniSpider):
    name = "�����̳�"
    url = "https://search.jd.com/Search?keyword={}&enc=utf-8&pvid=adc505dac9d2429a95b6da44b7575ead"
    captcha_uri = "https://mall.jd.com/sys/vc/createVerifyCode.html"
    cross_captcha_uri = "https://mall.jd.hk/sys/vc/createVerifyCode.html"
    license_uri = "https://mall.jd.com/showLicence-{}.html"
    search_uri = "https://search.jd.com/s_new.php?keyword={}&enc=utf-8&page=1"  # �ڶ�ҳ��ʼ
    instru_uri = "https://c0.3.cn/stock?skuId={}&venderId={}&callback=jQuery9683234&cat={}&area=17_1381_50718_0"  # ˵������
    score_uri = "https://mall.jd.com/view/getJshopHeader.html?callback=jQuery4335455&appId={}"
    tempGoodsSet = set()
    tempStoreSet = set()

    custom_settings = {
        "DOWNLOAD_DELAY": 1.5,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.163 Safari/537.36"
    }

    def start_requests(self):
        self.searchKey = self.crawler.settings.get("target")
        if not self.searchKey:
            raise Exception("δָ�������ؼ���")

        yield Request(self.url.format(self.searchKey), callback=self.patchCookies)

    def patchCookies(self, response):  # ��Ҫ����ת����ҳ��cookies
        search_uri = self.search_uri.format(self.searchKey)
        yield Request(search_uri)

    def captchaRequest(self, storeId, tryCount=0, document=None or {}, uri=None):
        """
        :param storeId: ����id
        :param tryCount: ��֤�����Դ���
        :return:
        """
        if tryCount > 5: return
        return Request(uri or self.captcha_uri, self.validCaptcha, priority=1, meta={
            "storeId": storeId,
            "dont_merge_cookies": True,
            "tryCount": tryCount,
            "document": deepcopy(document)
        }, dont_filter=True)

    def parse(self, response):
        goodsNew = storesNew = 0
        stores = response.xpath('//*[@id="J_goodsList"]//li[@class="gl-item"]')
        for store in stores:
            storeUrl = from_xpath(store, './/*[@class="p-shop"]//a/@href')
            if not storeUrl:
                continue
            storeUrl = response.urljoin(storeUrl)
            storeId = re.search('index-(\d+)\.html', storeUrl)
            if not storeId:
                continue
            storeId = storeId.group(1)
            goodsUrl = from_xpath(store, './/*[@class="p-img"]/a/@href')
            if not goodsUrl:
                continue
            goodsUrl = response.urljoin(goodsUrl)
            title = from_xpath(store, './/*[@class="p-img"]/a/@title')
            content = from_xpath(store, './/*[@class="p-name p-name-type-2"]', type=xt.analysis_article)
            storeName = from_xpath(store, './/*[@class="p-shop"]//a/text()')

            if goodsUrl not in self.tempGoodsSet:
                self.tempGoodsSet.add(storeId)
                image = []
                for img in store.xpath('.//*[@class="ps-main" or @class="p-img"]//img'):  # ���ֲ�ͬ��ҳ��ṹ
                    picUri = from_xpath(img, './/@data-lazy-img|.//@source-data-lazy-img')
                    if picUri:
                        picUri = response.urljoin(picUri)
                        image.append(img2base64(picUri))
                yield Request(goodsUrl, callback=self.goodsPageParse, priority=1, meta={
                    "document": {
                        "��Ʒ����": title,
                        "��Ʒ��ַ": goodsUrl,
                        "��Ʒ����": content,
                        "��Ʒ��ҳ��ͼ": None,
                        "����ͼƬ": image,
                        "��Ʒ���": None,
                        "��������": storeName,
                        "������ַ": storeUrl,
                        "����ʱ��": datetime.datetime.now(),
                        "����ID": storeId,
                        "�ۺ���Ϣ": {
                            "˵��": [],
                            "����˵��": []
                        },
                        "������Ϣ": {
                            "��Ʒ����": dict(),
                        }
                    }
                })
                goodsNew += 1
            if storeId not in self.tempStoreSet:
                self.tempStoreSet.add(storeId)
                document = {
                    "��������": storeName,
                    "������ַ": storeUrl,
                    "������ҳ��ͼ": None,
                    "�������": None,
                    "���ڵ�": None,
                    "��ҵ����": {
                        "֤����ͼ": []
                    },
                    "���̱�ǩ": None,
                    "���̶�̬����": dict(),
                    "����ʱ��": datetime.datetime.now(),
                    "����ID": storeId
                }
                yield self.captchaRequest(storeId, document=document)
                storesNew += 1
        self.log("��Ʒ��Ϣ: ��{}������{}��δ��".format(len(stores), goodsNew), logging.INFO)
        self.log("������Ϣ: ��{}������{}��δ��".format(len(stores), storesNew), logging.INFO)
        if goodsNew or storesNew:
            yield next_page_request(response, "page=(\d+)")

    def goodsPageParse(self, response):
        document = response.meta["document"]

        # �ۺ���Ϣ-˵��
        skuid = re.search("skuid:\s*(\d+?),", response.text).group(1)
        venderId = re.search("venderId:\s*(\d+?),", response.text).group(1)
        cat = re.search("cat:\s*\[(.+?)\]", response.text).group(1)
        instruction = requests.get(self.instru_uri.format(skuid, venderId, cat)).text
        document["�ۺ���Ϣ"]["˵��"].extend(re.findall('"showName":\s*"(.*?)"', instruction))

        # �ۺ���Ϣ-����˵��
        for instru in response.xpath('//*[@class="more-con"]//li'):
            document["�ۺ���Ϣ"]["����˵��"].append(from_xpath(instru, './/text()', type=xt.string_join))

        # ������Ϣ-��Ʒ����
        for goodsInfo in response.xpath('//*[@class="p-parameter"]//li'):
            key, value = re.search('(.*?)[:��](.*)', from_xpath(goodsInfo, './/text()', type=xt.string_join),
                                   re.S).groups()
            if all((key, value)):
                document["������Ϣ"]["��Ʒ����"][key.strip()] = value.strip()

    def validCaptcha(self, response):  # ��֤��ʶ��
        storeId = response.meta["storeId"]
        tryCount = response.meta["tryCount"]
        document = response.meta["document"]
        cookies = dict()
        for header, values in response.headers.items():
            if header == b"Set-Cookie":
                cookie = "".join([cookie.decode() for cookie in values])
                cookies['JSESSIONID'] = re.search('JSESSIONID=(.*?);', cookie).group(1)
                _jshop_vd_ = re.search('_jshop_vd_=(.*?);', cookie)
                if _jshop_vd_:  # ������֤��
                    cookies['_jshop_vd_'] = _jshop_vd_.group(1)
                _jshop_vd_hk_ = re.search('_jshop_vd_hk_=(.*?);', cookie)
                if _jshop_vd_hk_:  # �羳������֤��
                    cookies['_jshop_vd_hk_'] = _jshop_vd_hk_.group(1)
                break
        yield FormRequest(
            self.license_uri.format(storeId),
            formdata={
                "verifyCode": captcha(response.body)
            },
            meta={
                "storeId": storeId,
                "tryCount": tryCount,
                "document": document
            },
            cookies=cookies,
            callback=self.parseLicense
        )

    def parseLicense(self, response):
        storeId = response.meta["storeId"]
        tryCount = response.meta["tryCount"]
        document = response.meta["document"]
        if "��֤��" in response.text:
            self.log("��֤��ʧ����...����: {} storeId: {}".format(tryCount, storeId), logging.WARNING)
            if "�����̳����꾭Ӫ��������Ϣ" in response.text:
                yield self.captchaRequest(storeId, tryCount + 1, document=document)
            elif "�����������꾭Ӫ��������Ϣ" in response.text:  # ת�羳����
                self.log("ת�羳������֤��: {}".format(storeId))
                yield self.captchaRequest(storeId, tryCount + 1, document=document, uri=self.cross_captcha_uri)
            else:
                self.log("֤��ҳ��İ���, ��ǰurl: {}".format(response.url), logging.ERROR)
        elif "�����̳����꾭Ӫ��Ӫҵִ����Ϣ" in response.text \
                or "�����������꾭Ӫ��������Ϣ" in response.text:
            for picUri in response.xpath('//*[@class="qualification-img"]/@src').extract():
                picUri = response.urljoin(picUri)
                document["��ҵ����"]["֤����ͼ"].append(img2base64(picUri))
            for li in response.xpath('//*[@class="jScore"]//li'):
                text = from_xpath(li, './/text()', type=xt.string_join)
                key, value = re.search('(.*?)[:��](.*)', text, re.S).groups()
                if all((key, value)):
                    document["��ҵ����"][strip_all(key)] = strip_all(value)

            # �̵�����
            appId = from_xpath(response, '//*[@id="pageInstance_appId"]/@value')
            if appId:
                text = requests.get(self.score_uri.format(appId)).text
                for key, value in re.findall('(�û�����|������Լ|�ۺ����|����̬��)[:��].*?(\d+\.\d+)', text, re.S):
                    document["���̶�̬����"][key] = value
        else:
            self.log("������������ҳ����߸İ���, ��ǰurl: {}".format(response.url), logging.ERROR)


if __name__ == '__main__':
    target = ""
    MySpider.run(__file__, suffix=f"-s target={target} --loglevel INFO")
