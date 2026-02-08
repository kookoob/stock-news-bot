#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
웹사이트용 뉴스 수집 (이미지 없이)
"""

import feedparser
import requests
import os
import sys
import json
import time
from datetime import datetime, timezone
from bs4 import BeautifulSoup

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyDSkxDygLSc_UHOGzkKmegx_63ktbEtUYc")
OUTPUT_FILE = "../news-app/public/news.json"

RSS_SOURCES = [
    ("Reuters(Business)", "https://www.reuters.com/business/rss"),
    ("Reuters(Markets)", "https://www.reuters.com/markets/rss"),
    ("WSJ(Market)", "https://feeds.content.dowjones.io/public/rss/RSSMarketsMain"),
    ("Bloomberg", "https://feeds.bloomberg.com/markets/news.rss"),
    ("CNBC(Markets)", "https://www.cnbc.com/id/10000664/device/rss/rss.html"),
    ("Financial Times", "https://www.ft.com/rss/home"),
    ("MarketWatch", "https://feeds.marketwatch.com/marketwatch/marketpulse/"),
    ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
    ("Seeking Alpha", "https://seekingalpha.com/market_currents.xml"),
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
]

def fetch_news():
    """최신 뉴스 수집"""
    news_items = []
    
    # 필터링할 키워드
    skip_words = ['quiz', 'poll', '퀴즈', 'opinion', 'commentary', 'sponsored']
    
    for name, url in RSS_SOURCES:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:8]:  # 각 소스에서 8개씩
                title_lower = entry.title.lower()
                
                # 퀴즈/광고 필터링
                if any(word in title_lower for word in skip_words):
                    continue
                
                news_items.append({
                    'title': entry.title,
                    'link': entry.link,
                    'source': name.split('(')[0],
                    'published': entry.get('published', ''),
                })
        except Exception as e:
            print(f"❌ {name} 오류: {e}")
    
    return news_items[:30]  # 최대 30개

def translate_and_summarize(title, link):
    """Gemini로 번역 및 요약"""
    try:
        # 기사 내용 가져오기
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(link, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        paragraphs = soup.find_all('p')
        content = ' '.join([p.get_text() for p in paragraphs[:5]])[:1500]
        
        # Gemini API 호출
        prompt = f"""다음 영문 뉴스를 한글로 번역하고 투자자 관점에서 분석하세요.

제목: {title}
내용: {content}

규칙:
- 제목은 한글로만, 간결하게 1줄
- 요약은 투자 관점으로 2-3문장
- 상세 내용은 투자 인사이트 중심 3-4문단
- 관련 주식/지수/암호화폐 티커 추출 (최대 5개, 예: AAPL, ^DJI, BTC-USD)
- JSON 형식 엄수

JSON:
{{"title_ko":"번역된제목","summary":"요약","content":"상세내용","tickers":["AAPL","^DJI"]}}"""
        
        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}",
            headers={'Content-Type': 'application/json'},
            json={
                "contents": [{
                    "parts": [{"text": prompt}]
                }]
            },
            timeout=30
        )
        
        result = response.json()
        
        # 에러 체크
        if 'candidates' not in result or not result['candidates']:
            print(f"    ⚠️  Gemini 응답 없음: {result.get('error', 'Unknown')}")
            raise Exception("No candidates in response")
        
        text = result['candidates'][0]['content']['parts'][0]['text']
        
        # JSON 파싱 (제어 문자 제거)
        import re
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            json_str = json_match.group()
            # 제어 문자 제거
            json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', json_str)
            data = json.loads(json_str)
            return data
        
    except Exception as e:
        print(f"❌ 번역/요약 실패: {e}")
        # 간단한 제목 번역이라도 시도
        try:
            simple_prompt = f"다음 뉴스 제목을 한글 1줄로만 번역하세요. 설명 없이 번역만: {title}"
            resp = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}",
                headers={'Content-Type': 'application/json'},
                json={"contents": [{"parts": [{"text": simple_prompt}]}]},
                timeout=15
            )
            result = resp.json()
            if 'candidates' in result and result['candidates']:
                translated = result['candidates'][0]['content']['parts'][0]['text'].strip()
                # 첫 줄만 사용 (여러 옵션 제시 방지)
                translated = translated.split('\n')[0].strip('*-"\'')
                return {
                    "title_ko": translated,
                    "summary": "상세 요약을 준비 중입니다.",
                    "content": "원문을 확인하려면 아래 링크를 클릭하세요.",
                    "tickers": []
                }
        except:
            pass
        
        return {
            "title_ko": title,
            "summary": "요약 생성 실패",
            "content": "내용을 가져올 수 없습니다.",
            "tickers": []
        }

def main():
    print("=" * 60)
    print("📰 뉴스 수집 시작 (Gemini)")
    print("=" * 60)
    
    # 뉴스 수집
    print("1️⃣ RSS 피드 수집 중...")
    raw_news = fetch_news()
    print(f"✅ {len(raw_news)}개 수집")
    
    # 번역 및 요약
    print("\n2️⃣ Gemini 번역/요약 중...")
    processed_news = []
    
    max_process = min(10, len(raw_news))  # 최대 10개
    for i, item in enumerate(raw_news[:max_process], 1):
        print(f"   처리 중 {i}/{max_process}: {item['title'][:50]}...")
        result = translate_and_summarize(item['title'], item['link'])
        
        # 티커 추출 (Gemini + 키워드 매핑)
        tickers = result.get('tickers', []) or []
        
        # 키워드 기반 티커 추가
        text = (result['title_ko'] + ' ' + result['content']).lower()
        if '암호화폐' in text or '비트코인' in text or 'crypto' in item['title'].lower():
            tickers.extend(['BTC-USD', 'ETH-USD'])
        if '다우존스' in text or 'dow jones' in item['title'].lower():
            tickers.extend(['^DJI', '^GSPC'])
        if '나스닥' in text or 'nasdaq' in item['title'].lower():
            tickers.append('^IXIC')
        if 'block' in item['title'].lower() or '블록' in text:
            tickers.append('SQ')
        if '골드만' in text or 'goldman' in item['title'].lower():
            tickers.append('GS')
        if '애플' in text or 'apple' in item['title'].lower():
            tickers.append('AAPL')
        if '테슬라' in text or 'tesla' in item['title'].lower():
            tickers.append('TSLA')
        
        # 중복 제거 및 최대 5개
        tickers = list(set(tickers))[:5]
        
        processed_news.append({
            'id': f"news_{int(time.time())}_{i}",
            'title': result['title_ko'],
            'summary': result['summary'],
            'content': result['content'],
            'source': item['source'],
            'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'timestamp': int(time.time()) - (i * 60),
            'link': item['link'],
            'tickers': tickers
        })
        
        time.sleep(2)  # API rate limit
    
    # 기존 뉴스 불러오기
    print("\n3️⃣ 기존 뉴스 병합 중...")
    existing_news = []
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
                existing_news = json.load(f)
            print(f"   기존 뉴스: {len(existing_news)}개")
        except:
            pass
    
    # 중복 제거 (링크 기준)
    existing_links = {item['link'] for item in existing_news}
    new_items = [item for item in processed_news if item['link'] not in existing_links]
    
    print(f"   새 뉴스: {len(new_items)}개 (중복 {len(processed_news) - len(new_items)}개 제거)")
    
    # 병합 및 최신순 정렬
    all_news = new_items + existing_news
    all_news.sort(key=lambda x: x['timestamp'], reverse=True)
    
    # 최대 200개로 제한
    all_news = all_news[:200]
    
    # JSON 저장
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(all_news, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 완료! {OUTPUT_FILE}")
    print(f"📊 총 {len(all_news)}개 뉴스 저장 (최신 {len(new_items)}개 추가)")

if __name__ == "__main__":
    main()
