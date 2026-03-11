#!/usr/bin/env python3
"""
Simple GNO trade test with minimal code
"""
import os
import sys
import time
import json
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

# 프로젝트 경로 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.exchanges.bithumb import BithumbExchange

def main():
    api_key = os.getenv('BITHUMB_API_KEY')
    api_secret = os.getenv('BITHUMB_API_SECRET')
    
    exchange = BithumbExchange(api_key, api_secret)
    
    # Direct API call to test
    import requests
    import hashlib
    import hmac
    import base64
    import urllib.parse
    
    endpoint = '/trade/market_buy'
    nonce = str(int(time.time() * 1000))
    
    # Calculate units for 5,500 KRW
    krw_amount = 5500
    gno_price = 165400  # Current price from ticker
    units = round(krw_amount / gno_price, 4)  # 0.0333
    
    params = {
        'order_currency': 'GNO',
        'payment_currency': 'KRW',
        'units': str(units)
    }
    
    # Create signature
    data = endpoint + chr(0) + urllib.parse.urlencode(params) + chr(0) + nonce
    signature = hmac.new(
        api_secret.encode('utf-8'),
        data.encode('utf-8'),
        hashlib.sha512
    ).hexdigest()
    api_sign = base64.b64encode(signature.encode('utf-8')).decode('utf-8')
    
    headers = {
        'Api-Key': api_key,
        'Api-Sign': api_sign,
        'Api-Nonce': nonce,
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    url = f"https://api.bithumb.com{endpoint}"
    
    print(f"Request URL: {url}")
    print(f"Request Headers: {json.dumps(headers, indent=2)}")
    print(f"Request Params: {json.dumps(params, indent=2)}")
    print(f"Calculated units: {units} GNO for {krw_amount} KRW")
    
    response = requests.post(url, headers=headers, data=params)
    
    print(f"\nResponse Status: {response.status_code}")
    print(f"Response Headers: {dict(response.headers)}")
    
    try:
        response_data = response.json()
        print(f"Response Data: {json.dumps(response_data, indent=2, ensure_ascii=False)}")
    except:
        print(f"Response Text: {response.text}")

if __name__ == '__main__':
    main()