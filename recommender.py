import os, re, numpy as np, pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

def _to_datetime_safe(s):
    if pd.isna(s): return pd.NaT
    s = str(s).strip()
    for dayfirst in (True, False):
        try:
            return pd.to_datetime(s, dayfirst=dayfirst, errors="raise")
        except Exception:
            continue
    token = re.split(r"[ T]", s)[0]
    return pd.to_datetime(token, dayfirst=True, errors="coerce")

def _sanitize_topic(val: str) -> str:
    if pd.isna(val): return "default"
    s = str(val).strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    known = {"politics","sport","economy","tech","world","culture","default"}
    return s if s in known else "default"

class NewsRecommender:
    def __init__(self, csv_path: str):
        self.csv_path = csv_path
        self.NROWS = int(os.getenv("NEWS_NROWS", "50000"))
        self.MAX_TEXT = int(os.getenv("NEWS_MAX_TEXT", "2000"))
        self.TFIDF_FEATS = int(os.getenv("NEWS_TFIDF_FEATS", "2000"))
        self.df = self._load_df()
        self._build_index()

    def _load_df(self) -> pd.DataFrame:
        if not os.path.exists(self.csv_path):
            return pd.DataFrame([{
                "title": "Добро пожаловать в News Portal",
                "text": "Положите ваш dataset в data/news.csv — url,title,text,topic,tags,date",
                "topic": "welcome",
                "tags": "intro,portal",
                "date": "2024-01-01"
            }])
        df = pd.read_csv(self.csv_path, nrows=self.NROWS, low_memory=False)
        for c in ["title","text","tags","topic","url"]:
            if c in df.columns:
                df[c] = df[c].astype(str)
        if "text" in df.columns:
            df["text"] = df["text"].str.slice(0, self.MAX_TEXT)
        if "date" in df.columns:
            df["date_dt"] = df["date"].apply(_to_datetime_safe)
        else:
            df["date_dt"] = pd.NaT

        df["content"] = (
            df.get("title","").fillna("").astype(str) + " " +
            df.get("text","").fillna("").astype(str) + " " +
            df.get("tags","").fillna("").astype(str) + " " +
            df.get("topic","").fillna("").astype(str)
        )
        df = df.reset_index(drop=True)

        # ключ для изображений
        if "topic" in df.columns:
            df["topic_key"] = df["topic"].apply(_sanitize_topic)
        else:
            df["topic_key"] = "default"
        return df

    def _build_index(self):
        self.vectorizer = TfidfVectorizer(max_features=self.TFIDF_FEATS, stop_words="english")
        self.X = self.vectorizer.fit_transform(self.df["content"].tolist())

    def search(self, q: str) -> pd.DataFrame:
        if not q: return self.df
        q = str(q).strip()
        mask = (
            self.df["title"].str.contains(q, case=False, na=False) |
            self.df["text"].str.contains(q, case=False, na=False) |
            self.df["tags"].str.contains(q, case=False, na=False)
        )
        sub = self.df[mask]
        if len(sub) == 0:
            q_vec = self.vectorizer.transform([q])
            sims = cosine_similarity(q_vec, self.X).ravel()
            order = np.argsort(-sims)[:100]
            sub = self.df.iloc[order]
        return sub

    def recommend(self, article_id: int, top_k: int = 5):
        if article_id < 0 or article_id >= len(self.df): return []
        sims = cosine_similarity(self.X[article_id], self.X).ravel()
        sims[article_id] = -1.0

        topic_self = str(self.df.loc[article_id].get("topic", "")).strip().lower()
        if topic_self:
            same_topic = self.df["topic"].fillna("").str.lower().eq(topic_self).values.astype(float)
            sims += 0.05 * same_topic

        dates = self.df.get("date_dt")
        if dates is not None:
            now = pd.Timestamp.now()
            age_days = (now - dates).dt.days.replace([pd.NaT], np.nan)
            age_days = age_days.fillna(age_days.max() if age_days.notna().any() else 365)
            decay = np.exp(-age_days / 365.0)
            sims = sims * decay.values

        order = np.argsort(-sims)[:top_k]
        return [{"id": int(i), "score": float(sims[i])} for i in order]

    def analytics(self):
        charts = {}
        # Топ тем
        if "topic" in self.df.columns:
            top_topics = (self.df["topic"].fillna("Unknown").value_counts().head(10))
            charts["topics"] = top_topics.to_dict()

        # Таймлайн по месяцам
        if "date_dt" in self.df.columns and self.df["date_dt"].notna().any():
            tmp = self.df[self.df["date_dt"].notna()].copy()
            tmp["ym"] = tmp["date_dt"].dt.to_period("M")
            ts = tmp.groupby("ym").size().sort_index()
            charts["timeline"] = {str(k): int(v) for k, v in ts.items()}

        # Топ-теги: tags или fallback из title/text
        from collections import Counter
        cnt = Counter()
        if "tags" in self.df.columns and self.df["tags"].notna().any():
            for s in self.df["tags"].dropna().astype(str):
                for p in re.split(r"[,;\\s]+", s):
                    p = p.strip().lower()
                    if len(p) >= 3:
                        cnt[p] += 1
        else:
            stop = set("""the a an to of for and or is are be on in at with by from as this that those these into over under about it its was were been being our your their them they you we i he she his her not no yes if then else when where who whom which will would can could should may might one two three new latest breaking update said more just""".split())
            texts = []
            if "title" in self.df.columns:
                texts.extend(self.df["title"].dropna().astype(str).tolist())
            if "text" in self.df.columns:
                texts.extend(self.df["text"].dropna().astype(str).tolist())
            for s in texts:
                for p in re.findall(r"[a-zA-Z]{3,}", s.lower()):
                    if p not in stop:
                        cnt[p] += 1
        charts["top_tags"] = dict(cnt.most_common(20))
        return charts
