from flask import Flask, render_template, request
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
import time
from datetime import datetime, timedelta
from webdriver_manager.chrome import ChromeDriverManager
import google.generativeai as genai
import sqlite3

app = Flask(__name__)

# OpenAI API 설정
GOOGLE_API_KEY = 'AIzaSyBlEWYCjt1LSc_r1sykPJS8-7rGrEcyLRc'
genai.configure(api_key=GOOGLE_API_KEY)
generation_config = {
    "temperature": 0.9,
    "top_p": 1,
    "top_k": 1,
    "max_output_tokens": 2048,
}
model = genai.GenerativeModel('gemini-pro', generation_config=generation_config)

# 데이터베이스 초기화
def init_db():
    conn = sqlite3.connect('articles.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY,
                stance TEXT,
                paper TEXT,
                title TEXT,
                time TEXT,
                content TEXT,
                link TEXT,
                summary TEXT
                )''')
    conn.commit()
    conn.close()

# 기사 데이터 저장
def save_to_db(data):
    conn = sqlite3.connect('articles.db')
    c = conn.cursor()
    for article in data:
        c.execute('''INSERT INTO articles (stance, paper, title, time, content, link, summary) VALUES (?, ?, ?, ?, ?, ?, ?)''', 
        (article['stance'], article['paper'], article['title'], article['time'], article['content'], article['link'], article.get('summary', '')))
    conn.commit()
    conn.close()

# 데이터베이스에서 기사 가져오기
def get_articles_from_db(keyword):
    conn = sqlite3.connect('articles.db')
    c = conn.cursor()
    c.execute('''SELECT * FROM articles WHERE content LIKE ?''', ('%' + keyword + '%',))
    articles = c.fetchall()
    conn.close()
    return articles

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search():
    keyword = request.form['keyword']
    
    # 크롬 드라이버 자동 설치 및 설정
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    # 신문사 별 oid
    papers = {
        "진보": [("한겨레", "028"), ("경향신문", "032")],
        "중도": [("서울신문", "081"), ("한국일보", "469")],
        "보수": [("조선일보", "023")]
    }

    # 오늘 날짜 및 14일 전 날짜 설정
    end_date = datetime.today()
    start_date = end_date - timedelta(days=14)

    # 빈 리스트 생성
    all_articles = []

    # 날짜 범위 내에서 반복
    for single_date in (start_date + timedelta(n) for n in range(14)):
        formatted_date = single_date.strftime("%Y%m%d")
        
        for stance, paper_list in papers.items():
            for paper_name, oid in paper_list:
                url = f"https://news.naver.com/main/list.naver?mode=LPOD&mid=sec&oid={oid}&listType=title&date={formatted_date}"
                driver.get(url)
                
                # 페이지 소스를 BeautifulSoup로 파싱
                soup = BeautifulSoup(driver.page_source, 'html.parser')

                # 기사 제목과 링크 추출
                articles = soup.find_all('a', class_='nclicks(cnt_flashart)')
                for index, article in enumerate(articles, start=1):
                    title = article.text.strip()  # 기사 제목 추출
                    link = article['href']  # 기사 링크 추출

                    # 기사 제목에 키워드가 1번 이상 포함되어 있는지 확인
                    if keyword in title:
                        # 기사 페이지로 이동하여 기사 내용 및 시간 추출
                        driver.get(link)
                        time.sleep(1)
                        try:
                            temp_article = driver.find_element(By.CSS_SELECTOR, '#newsct_article').text
                        except:
                            try:
                                temp_article = driver.find_element(By.CSS_SELECTOR, '._article_content').text
                            except:
                                continue  # 내용이 없으면 건너뜀

                        # 기사 내용에 키워드가 2번 이상 포함되어 있는지 확인
                        if temp_article.count(keyword) >= 2:
                            # 시간 정보 추출
                            try:
                                # 스포츠 뉴스가 아닌 경우
                                time_e = driver.find_element(By.CSS_SELECTOR, '.media_end_head_info_datestamp_time').text
                            except:
                                try:
                                    # 스포츠 뉴스인 경우
                                    time_e = driver.find_element(By.CSS_SELECTOR, '.NewsEndMain_date__xjtsQ').text
                                except:
                                    time_e = "시간 정보 없음"

                            # 데이터 저장
                            all_articles.append({
                                'stance': stance,
                                'paper': paper_name,
                                'title': title,
                                'time': time_e,
                                'content': temp_article,
                                'link': link
                            })

    # 브라우저 종료
    driver.quit()

    # 데이터가 있을 경우 Gemini API로 요약 생성
    if all_articles:
        for article in all_articles:
            temp_article = article['content']
            prompt = f"다음 기사를 세 줄로 요약해줘:\n{temp_article}"
            response = model.generate_content(prompt)
            article['summary'] = response.text.strip() if response.text else "요약 실패"
        
        # 데이터베이스에 저장
        save_to_db(all_articles)
    else:
        return "최근 14일 기준으로 해당 키워드가 포함된 기사가 없습니다."

    return render_template('results.html', keyword=keyword, articles=all_articles)

if __name__ == '__main__':
    init_db()
    app.run(debug=True)



