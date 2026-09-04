# 近江八幡市 くらし更新だより(非公式)

近江八幡市に関連する複数サイトの新着情報を自動収集し、
RSS(rss.xml)とWebサイト(index.html / GitHub Pages)で公開する仕組み。

## 収集対象と方式

| 出典 | 方式 |
|---|---|
| 近江八幡市公式サイト | ハブページ監視(hubs.jsonの部署ページ等を巡回) |
| 近江八幡経済新聞 | 公式RSS取得 |
| 号外NET(東近江市・近江八幡市) | 公式RSS取得(タイトルに「近江八幡」を含む記事のみ) |
| 近江八幡市立総合医療センター | 公式RSS取得 |
| 近江八幡市観光サイト(omi8.com) | ハブページ監視(9カテゴリ一覧を巡回) |
| 近江八幡市立図書館 | ハブページ監視(トップ・図書館だより一覧を巡回) |
| 近江八幡警察署(滋賀県警) | 1ページ追記型を日付で分割して取得 |

全記事に「出典：◯◯」が付与される(RSSはタイトル末尾、Webサイトは記事の下)。

## ファイル構成

| ファイル | 役割 | 実行順 |
|---|---|---|
| common.py | 全スクリプト共通の処理(通信・文字コード・XML補正・重複管理) | - |
| discover_hubs.py | 市サイトの部署ページ一覧(hubs.json)を作成 | 月1回 |
| watch_hubs_and_generate_rss.py | 市サイトの新着収集 | 1 |
| fetch_rss_sources.py | 公式RSSを持つ3サイトの新着収集 | 2 |
| watch_hub_sources.py | 観光サイト・図書館の新着収集 | 3 |
| fetch_shiga_police_omihachiman.py | 警察署の活動ページの新着収集 | 4 |
| build_feed.py | 収集結果からrss.xmlを生成(日付順に整列) | 5 |
| index.html | 公開Webサイト(rss_items.jsonを表示) | - |

収集スクリプト(1〜4)はデータファイルを更新するだけで、rss.xmlは
最後のbuild_feed.pyだけが生成する。1つのサイトで取得に失敗しても
他のサイトの収集とRSS生成は止まらない。

## 自動生成されるファイル(手で編集しない)

- hubs.json : 市サイトの巡回対象一覧
- known_links.json : 既知記事の一覧(重複防止)
- rss_items.json : 収集した記事データ(Webサイトの表示元)
- rss.xml : RSSフィード(Feedlyに登録するのはこれ)
- feed_fingerprint.txt : 前回生成時の内容記録(無変更時のコミット抑制用)

## 公開URL

- Webサイト: https://sudanie2.github.io/omihachiman-rss/
- RSS: https://sudanie2.github.io/omihachiman-rss/rss.xml

## 収集対象外としたサイトと理由

- 滋賀報知新聞 / 京都新聞: robots.txtによる自動アクセス拒否+有料報道コンテンツのため
  (京都新聞はGoogleニュースRSSでFeedly個人購読のみ。公開サイトへの組込はGoogle規約上不可)
