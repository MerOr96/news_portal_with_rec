from flask import Flask, render_template, request, abort
from recommender import NewsRecommender
import os
from math import ceil

app = Flask(__name__)

CSV_PATH = os.path.join("data", "news.csv")
recommender = NewsRecommender(CSV_PATH)

def get_pagination(page, per_page, total):
    """Создает объект пагинации"""
    pages = ceil(total / per_page) if total > 0 else 1
    page = max(1, min(page, pages))
    
    class Pagination:
        def __init__(self, page, per_page, total, pages):
            self.page = page
            self.per_page = per_page
            self.total = total
            self.pages = pages
            self.has_prev = page > 1
            self.has_next = page < pages
            self.prev_num = page - 1 if self.has_prev else None
            self.next_num = page + 1 if self.has_next else None
        
        def iter_pages(self, left_edge=2, right_edge=2, left_current=2, right_current=2):
            last = self.pages
            for num in range(1, last + 1):
                if num <= left_edge or \
                   (num > self.page - left_current - 1 and num < self.page + right_current) or \
                   num > last - right_edge:
                    yield num
    
    return Pagination(page, per_page, total, pages)

def get_topics():
    """Получает список всех тем"""
    if "topic" in recommender.df.columns:
        topics = recommender.df["topic"].dropna().unique().tolist()
        return sorted([t for t in topics if t and str(t).strip()])
    return []

@app.route("/")
def index():
    page = request.args.get("page", 1, type=int)
    sort_by = request.args.get("sort", "date_desc")
    per_page = 24
    
    df = recommender.df.copy()
    df["id"] = df.index
    
    # Сортировка
    if "date_dt" in df.columns and sort_by.startswith("date"):
        ascending = sort_by == "date_asc"
        df = df.sort_values("date_dt", ascending=ascending, na_position="last")
    elif sort_by.startswith("title") and "title" in df.columns:
        ascending = sort_by == "title_asc"
        df = df.sort_values("title", ascending=ascending, na_position="last")
    elif "date_dt" in df.columns:
        df = df.sort_values("date_dt", ascending=False, na_position="last")
    
    total = len(df)
    pagination = get_pagination(page, per_page, total)
    
    start = (page - 1) * per_page
    end = start + per_page
    articles = df.iloc[start:end].to_dict(orient="records")
    
    topics = get_topics()
    
    return render_template("index.html", 
                         articles=articles, 
                         pagination=pagination,
                         topics=topics,
                         current_sort=sort_by)

@app.route("/search")
def search():
    q = request.args.get("q", "").strip()
    page = request.args.get("page", 1, type=int)
    per_page = 24
    
    if q:
        df = recommender.search(q)
    else:
        df = recommender.df.copy()
    
    df = df.copy()
    df["id"] = df.index
    
    if "date_dt" in df.columns:
        df = df.sort_values("date_dt", ascending=False, na_position="last")
    
    total = len(df)
    pagination = get_pagination(page, per_page, total)
    
    start = (page - 1) * per_page
    end = start + per_page
    articles = df.iloc[start:end].to_dict(orient="records")
    
    topics = get_topics()
    
    return render_template("index.html", 
                         articles=articles, 
                         query=q,
                         pagination=pagination,
                         topics=topics)

@app.route("/topic/<topic>")
def by_topic(topic):
    page = request.args.get("page", 1, type=int)
    per_page = 24
    
    df = recommender.df[recommender.df["topic"].fillna("").str.lower() == topic.lower()]
    df = df.copy()
    df["id"] = df.index
    
    if "date_dt" in df.columns:
        df = df.sort_values("date_dt", ascending=False, na_position="last")
    
    total = len(df)
    pagination = get_pagination(page, per_page, total)
    
    start = (page - 1) * per_page
    end = start + per_page
    articles = df.iloc[start:end].to_dict(orient="records")
    
    topics = get_topics()
    
    return render_template("index.html", 
                         articles=articles, 
                         current_topic=topic,
                         pagination=pagination,
                         topics=topics)

@app.route("/article/<int:article_id>")
def article(article_id):
    if article_id not in recommender.df.index:
        abort(404)
    
    article = recommender.df.loc[article_id].to_dict()
    recs = recommender.recommend(article_id, top_k=6)
    rec_cards = []
    
    for r in recs:
        aid = r["id"]
        if aid in recommender.df.index:
            row = recommender.df.loc[aid]
            rec_cards.append({
                "id": int(aid),
                "title": str(row.get("title", ""))[:140] or f"Article {aid}",
                "topic": str(row.get("topic", "")),
                "topic_key": str(row.get("topic_key", "default")),
                "date": str(row.get("date", "")),
                "score": float(r.get("score", 0.0))
            })
    
    return render_template("article.html", article=article, recs=rec_cards)

@app.route("/analytics")
def analytics():
    charts = recommender.analytics()
    return render_template("analytics.html", charts=charts)

@app.errorhandler(404)
def not_found(error):
    return render_template("404.html"), 404

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
