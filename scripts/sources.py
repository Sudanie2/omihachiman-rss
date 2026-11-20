#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
収集先サイトの設定をまとめたファイル(処理の中身は書かない)。

新しいサイトを追加するときは、該当する一覧に項目を1つ足すだけでよい。
  - RSS_SOURCES     : 公式RSS/Atomがある
  - LIST_SOURCES    : 一覧ページを解析する(RSSなし)
  - HUB_SOURCES     : 一覧ページから個別記事を辿る
  - SECTION_SOURCES : ページ内の目印の間にあるリンクを集める

項目の意味は各スクリプトの先頭の説明と、各項目のコメントを参照。
"""

# ==== RSSを配信しているサイト(fetch_rss_sources.py が使う) ====
RSS_SOURCES = [
    {
        "name": "近江八幡経済新聞",
        # 注意: /rss.html は「RSSについて」の説明ページ(HTML)。実際のフィードは /rss.xml
        "url": "https://omihachiman.keizai.biz/rss.xml",
        "title_filter": None,
    },
    {
        "name": "号外NET",
        "url": "https://higashiomi-omihachiman.goguynet.jp/feed/",
        "title_filter": "近江八幡",  # このキーワードを含むタイトルだけ採用
    },
    {
        "name": "近江八幡市立総合医療センター",
        "url": "https://www.kenkou1.com/news.xml",
        "title_filter": None,
    },
    {
        "name": "近江八幡市立資料館・かわらミュージアム",
        "url": "https://www.omihachiman-shiryoukan-kawara.jp/feed/",
        "title_filter": None,
    },
    {
        "name": "日牟禮八幡宮",
        "url": "https://himure.jp/news/feed/",
        "title_filter": None,
        # サイトに「無断で転載・複製を行なうことはできません」と明記があるため、
        # 本文の要約は保存せず、タイトルとリンクのみを扱う。
        "no_summary": True,
    },
    {
        "name": "近江八幡市社会福祉協議会",
        "url": "https://ohshakyo.or.jp/files/rss/block614.xml",  # お知らせ
        "title_filter": None,
    },
    {
        "name": "シガブンシンブン(滋賀県文化財保護協会)",
        # 「近江八幡市」で検索した結果をRSS化したもの(WordPressの検索フィード)
        "url": "https://www.shiga-bunkazai.jp/shigabun-shinbun/?s=%E8%BF%91%E6%B1%9F%E5%85%AB%E5%B9%A1%E5%B8%82&feed=rss2",
        "title_filter": None,
    },
    {
        "name": "安土城考古博物館長のつぶやき",
        "url": "https://azuchi-museum.blogspot.com/feeds/posts/default",
        "title_filter": None,
    },
    {
        "name": "安土文芸の郷",
        "url": "http://bungei.or.jp/files/rss/block6.xml",  # ニュース＆お知らせ
        "title_filter": None,
    },
    {
        "name": "安土文芸の郷",
        "url": "http://bungei.or.jp/files/rss/block70.xml",  # 事業・活動のご報告
        "title_filter": None,
    },
    {
        "name": "ヴォーリズ遺産を守る市民の会",
        # WordPress.com の標準フィード。robots.txt でも禁止されていない。
        "url": "https://voriesisan.wordpress.com/feed/",
        "title_filter": None,
        # タイトルとリンクのみを扱い、本文の要約は保存しない。
        "no_summary": True,
    },
    {
        "name": "特定非営利活動法人Since",
        # WordPress の「お知らせ」フィード。robots.txt でも禁止されていない。
        "url": "https://since.or.jp/news/feed/",
        "title_filter": None,
        # タイトルとリンクのみを扱い、本文の要約は保存しない。
        "no_summary": True,
    },
    {
        "name": "近江八幡市文化会館",
        # WordPress の標準フィード。「みつける一覧」(/blog/)と同じ記事
        # (お知らせ・イベント・公演)が配信される。robots.txt でも禁止されていない。
        "url": "https://omi8man-ch.jp/feed/",
        "title_filter": None,
        # タイトルとリンクのみを扱い、本文の要約は保存しない。
        "no_summary": True,
    },
]

# ==== RSSが無く、一覧ページを解析するサイト(fetch_list_sources.py が使う) ====
LIST_SOURCES = [
    {
        "name": "近江八幡商工会議所",
        "base": "https://8cci.com",
        "url": "https://8cci.com/topics/",
        # 一覧に出てくるカテゴリタグ(タイトル先頭から取り除く)
        "tags": [
            "お知らせ", "販路開拓", "検定", "セミナー", "補助金",
            "相談会", "創業支援", "保険・共済", "支援金", "事業承継",
        ],
        # このタグの記事だけ採用する(Noneなら全件)
        "tag_filter": ["お知らせ", "補助金"],
        # 記事リンクと判定するURLパターン(Noneならタグで判定)
        "link_pattern": None,
        # URLから取り除くクエリ(同じ記事が別URL扱いになるのを防ぐ)
        "drop_query": [],
    },
    {
        "name": "ボーダレス・アートミュージアムNO-MA",
        "base": "https://no-ma.jp",
        "url": "https://no-ma.jp/news/",
        "tags": [],
        "tag_filter": None,
        "link_pattern": r"^/20\d{2}/\d{2}/\d{2}/",
        "drop_query": [],
    },
    {
        "name": "近江八幡音楽祭",
        "base": "https://omihachiman-classicfes.jp",
        "url": "https://omihachiman-classicfes.jp/news",
        "tags": [],
        "tag_filter": None,
        "link_pattern": r"/news/\d+\.html",
        "drop_query": [],
    },
    # 近江八幡市社会福祉協議会「お知らせ」ページ(複数の掲載枠をまとめて表示している)。
    # 公式のRSSは枠ごとに分かれており、広報紙の枠(b_id=149)の最新号が
    # 反映されないことがあるため、一覧ページから広報紙の記事だけを補う。
    # (お知らせの枠 b_id=614 の記事はRSSで取得できているので対象外)
    {
        "name": "近江八幡市社会福祉協議会",
        "base": "https://ohshakyo.or.jp",
        "url": "https://ohshakyo.or.jp/pages/176/",
        "tags": [],
        "tag_filter": None,
        "link_pattern": r"/b_id=149/r_id=\d+",
        "drop_query": [],
        "strip_fragment": True,
        "item_selector": "div.record",
        "date_selector": "div.date",
        "title_selector": "span.title",
        "min_date": "2026-09-01",
    },
    {
        "name": "近江八幡地域勤労者福祉サービスセンター",
        "base": "https://www.workpia-omi-hachiman.jp",
        "url": "https://www.workpia-omi-hachiman.jp/info",
        "tags": [],
        "tag_filter": None,
        "link_pattern": r"/info/detail\?id=\d+",
        "drop_query": [],
    },
    # 八幡山ロープウェー(近江鉄道)
    # 記事URLの形式が一定でない(/ropeway/info/… /file.jsp?id=… 外部リンク)ため、
    # URLの形ではなく「近くに日付があるリンク」を記事とみなす(require_date)。
    {
        "name": "八幡山ロープウェー",
        "base": "https://www.ohmitetudo.co.jp",
        "url": "https://www.ohmitetudo.co.jp/icoico/event/list/?business=%E5%85%AB%E5%B9%A1%E5%B1%B1%E3%83%AD%E3%83%BC%E3%83%97%E3%82%A6%E3%82%A7%E3%83%BC",
        "tags": [],
        "tag_filter": None,
        "link_pattern": None,
        "drop_query": [],
        "require_date": True,
    },
    {
        "name": "八幡山ロープウェー",
        "base": "https://www.ohmitetudo.co.jp",
        "url": "https://www.ohmitetudo.co.jp/info/index.html?office-category-name=%E5%85%AB%E5%B9%A1%E5%B1%B1%E3%83%AD%E3%83%BC%E3%83%97%E3%82%A6%E3%82%A7%E3%83%BC",
        "tags": [],
        "tag_filter": None,
        "link_pattern": None,
        "drop_query": [],
        "require_date": True,
    },
    {
        "name": "八幡山ロープウェー",
        "base": "https://www.ohmitetudo.co.jp",
        "url": "https://www.ohmitetudo.co.jp/news/index.html?office-category-name=%E5%85%AB%E5%B9%A1%E5%B1%B1%E3%83%AD%E3%83%BC%E3%83%97%E3%82%A6%E3%82%A7%E3%83%BC",
        "tags": [],
        "tag_filter": None,
        "link_pattern": None,
        "drop_query": [],
        "require_date": True,
    },
    {
        "name": "近江八幡市立健康ふれあい公園",
        "base": "https://www.omi8man-kenkofureai.jp",
        "url": "https://www.omi8man-kenkofureai.jp/news/index.html",
        "tags": [],
        "tag_filter": None,
        "link_pattern": r"/news/detail\.php",
        # ref=/news/index.html は遷移元を示すだけなので除去する
        "drop_query": ["ref"],
    },
    # web滋賀プラスワン(滋賀県の広報サイト)の「近江八幡市」検索結果。
    # 一覧に日付は無いため、初めて見つけた日を掲載日とする。
    # 1つのリンクの中にタイトルと本文の冒頭が両方入っているので、
    # タイトルは title_selector で指定した要素の文字だけを使う。
    {
        "name": "web滋賀プラスワン",
        "base": "https://shigaplusone.jp",
        "url": "https://shigaplusone.jp/?s=%E8%BF%91%E6%B1%9F%E5%85%AB%E5%B9%A1%E5%B8%82",
        "tags": [],
        "tag_filter": None,
        "link_pattern": r"/(?:information/\d{6}_\d+|post/[^/]+)/",
        "drop_query": [],
        "title_selector": "p.result-list-textBlock-title",
        # 初回登録時に日付を指定する記事(一覧に日付が無いため手動で指定)
        "date_overrides": {
            "https://shigaplusone.jp/information/202608_112/": "2026-09-02",  # 「幻の安土城」復元プロジェクト・歴史セミナー
            "https://shigaplusone.jp/information/202608_102/": "2026-09-03",  # VRで安土城を探検しよう!
            "https://shigaplusone.jp/information/202609_015/": "2026-09-18",  # 滋賀で一緒に保育しよ!保育のしごと相談会
        },
        # 8月以前の記事のため登録しない
        "ignore_urls": [
            "https://shigaplusone.jp/information/202608_108/",
            "https://shigaplusone.jp/post/biwapochi/",
            "https://shigaplusone.jp/information/202606_120/",
            "https://shigaplusone.jp/post/shiga-locarion-ofice/",
            "https://shigaplusone.jp/information/202605_111/",
            "https://shigaplusone.jp/post/kokyo_sakamai/",
            "https://shigaplusone.jp/information/202604_208/",
        ],
    },
    # 広報おうみはちまん(市公式サイトの年度ページ)。号ごとに見出しとPDFが並ぶ。
    # マイ広報紙(mykoho.jp)はロボットからのアクセスだと一覧が表示されず、
    # 取得できないことがあるため、市の年度ページから号の追加を検知する。
    # 年度が変わると(毎年4月)ページのURLが変わるため、その時に url を差し替える。(要確認)
    {
        "name": "広報おうみはちまん",
        "kind": "issue_pdf",
        "base": "https://www.city.omihachiman.lg.jp",
        "url": "https://www.city.omihachiman.lg.jp/soshiki/hisho_koho/3/3/41373.html",
        "heading_pattern": r"広報おうみはちまん\d{1,2}月号",
        "min_date": "2026-09-01",
    },
    # 広報おうみはちまん(マイ広報紙 mykoho.jp)のバックナンバー一覧。
    # ページ上部の「最新号の記事を全部見る」も同じURLを指すため、
    # container_selector でバックナンバーの一覧の中だけを見る。
    # 一覧に日付は無く、タイトルが「広報おうみはちまん 2026年10月号」の形なので、
    # 「年・月」から掲載日(その月の1日)を決める(title_date_pattern)。
    # min_date より前の号は登録しない(過去の号を大量に登録しないため)。
    {
        "name": "広報おうみはちまん",
        "base": "https://mykoho.jp",
        "url": "https://mykoho.jp/lg/252042/577029",
        "tags": [],
        "tag_filter": None,
        "link_pattern": r"/koho/252042/\d+",
        "drop_query": [],
        "container_selector": "#jichitaiBacknum",
        "title_selector": "p",
        "title_date_pattern": r"(20\d{2})年\s*(\d{1,2})月号",
        "min_date": "2026-09-01",
    },
    # webアミンチュ(びわ湖放送のウェブメディア)のタグ「近江八幡市」の記事一覧。
    # 1件ごとの枠(article)の中に、サムネイル用・カテゴリ用・タイトル用など
    # 複数のリンクが入っている。文字のあるタイトルのリンクだけを記事とみなし、
    # 日付は同じ枠の中の日付(2026/08/04 形式)から取る(item_selector / date_selector)。
    # タイトルと日付だけを載せ、要約は載せない。
    {
        "name": "webアミンチュ",
        "base": "https://www.webaminchu.jp",
        "url": "https://www.webaminchu.jp/tag/hachiman/",
        "tags": [],
        "tag_filter": None,
        "link_pattern": r"/news/\d+/",
        "drop_query": [],
        "item_selector": "article.p-entries-item",
        "date_selector": "span.p-entries-day",
        "min_date": "2026-09-01",
    },
    # 近江八幡市立図書館(2026年10月にサイトが刷新され、記事のURLが変わった)。
    # トップページに「重要なお知らせ」「お知らせ」「イベント」「コーナー展示」
    # (と「おはなし会」)の最新分が並ぶ。おはなし会(/ohanashi/)は対象外。
    #   重要なお知らせ : /news2/?id=○   お知らせ : /news/?id=○
    #   コーナー展示   : /tenji/?id=○   イベント : /event/?id=○ (要確認:
    #   刷新直後で開催予定が無く、実際のURLの形を確認できていない)
    # 各リンクの中に「2026年10月3日 更新」の形で日付があり、タイトルは
    # span.title(お知らせ類)または p.linktit(イベント・展示)に入っている。
    # 旧サイトの記事は watch_hub_sources.py で取得していたが、URLが変わったため
    # そちらの図書館の設定は削除した。
    {
        "name": "近江八幡市立図書館",
        "base": "https://library.city.omihachiman.shiga.jp",
        "url": "https://library.city.omihachiman.shiga.jp/",
        "tags": [],
        "tag_filter": None,
        "link_pattern": r"/(?:news2?|event|tenji)/\?id=\d+",
        "drop_query": [],
        "title_selector": "span.title, p.linktit",
        # 刷新前の「9月のコーナー展示」を新着として登録しないため、10月以降だけ対象にする
        "min_date": "2026-10-01",
    },
]

# ==== ハブページ(一覧)を巡回して個別記事を見つけるサイト(watch_hub_sources.py が使う) ====
HUB_SOURCES = [
    {
        "name": "近江八幡市観光サイト",
        "base": "https://www.omi8.com",
        # 公共性のある情報のみを対象にする。
        # グルメ・土産・宿泊は個別店舗の紹介で、更新日の記載もなく
        # 新着かどうかも判別できないため対象外とする(下のexclude_patternで除外)。
        # 特集・モデルコース・スポット・イベントは、記事ページに日付の記載が無い。
        # 新着順に並ぶ一覧ページ(index_1_0____0___.html)を先に巡回することで、
        # 一覧の並び順をそのまま公開順として保てるようにする。
        "hubs": [
            "/stories/index_1_0____0___.html",      # 特集(新着順)
            "/course/index_1_0____0___.html",       # モデルコース(新着順)
            "/spot/index_1_0____0___.html",         # スポット・体験(新着順)
            "/event/index_1_0____0___.html",        # イベント(新着順)
            "/news/index.html",                     # お知らせ
            "/stories/index_1_2__11__0___.html",    # はちまん観光ライター
            "/pamphlet/index.html",                 # パンフレット
            "/index.html",                          # トップ(Pick up!)
        ],
        # 個別記事とみなすURLパターン
        "detail_pattern": r"/detail[_.]",
        # 個別店舗の紹介は収集しない
        "exclude_pattern": r"^/(restaurant|souvenir|stay|access|favorite)/",
    },
]

# ==== ページ内の指定範囲のリンクを集めるサイト(fetch_section_links.py が使う) ====
SECTION_SOURCES = [
    {
        "name": "安土学区まちづくり協議会",
        "base": "https://www.zd.ztv.ne.jp",
        "url": "https://www.zd.ztv.ne.jp/azuchi-cc/index.html",
        # この文字列の間にあるリンクを対象にする(表記ゆれに備え候補を複数持つ)
        # 「まち協．お知らせ」という文字の目印は実在しないことが判明(実HTMLで確認)。
        # 見出しが画像("images/mayikyo-osirase.gif")になっているため、そちらを使う。
        "start_marker_img_src": ["mayikyo-osirase", "matikyo-osirase"],
        "end_markers": ["連絡事項2", "連絡事項２"],
        # 対象とする拡張子(イベント告知は画像やPDFの場合もある)
        "allowed_ext": [".pdf", ".html", ".htm", ".jpg", ".jpeg", ".png", ".gif", ""],
    },
]
