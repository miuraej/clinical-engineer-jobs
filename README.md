# CE CAREER — 臨床工学技士 採用情報

病院公式サイトの臨床工学技士募集を定期確認する、GitHub Pages用の静的サイトです。
公開予定: https://miuraej.github.io/clinical-engineer-jobs/

## 公開手順

1. `miuraej` のアカウントで Public リポジトリ `clinical-engineer-jobs` を作成します。
2. このフォルダーの内容を main ブランチへアップロードします。`.github/workflows/update-and-deploy.yml` も必要です。
3. Settings → Pages → Build and deployment → Source で **GitHub Actions** を選択します。
4. Settings → Actions → General で Actions の実行を許可します。ブランチ保護などで自動データ更新が拒否される場合は、Actionsのエラーを確認してください。
5. Actions → Collect and publish recruitment information → Run workflow を実行します。
6. deploy ジョブの成功後、公開予定URLを開きます。

GitHub Actionsは毎日日本時間6:23（UTC 21:23）、mainへの変更、手動実行で動作します。定期実行は遅延や欠落があり得ます。公開リポジトリは60日間操作がないと定期実行が無効化されることがあるため、Actionsで有効状態を確認してください。サイトは確認から3日以上経過した情報を「要確認」と表示します。

## できること

- 病院名・地域・雇用形態などのキーワード検索、地域・掲載状況による絞り込み
- 公式募集ページへのリンク、明確な募集期限、最終確認日時
- 期限経過・終了情報と、取得できなかった情報の区別
- 取得エラー時は以前の情報と最終確認日時を維持
- スマートフォン対応、キーボード操作、読み込み失敗・検索0件の表示
- 収集データをJSONとして保存し、Actionsで更新・公開

## 収集対象と制限

初期設定は `sources.json` の9ページ（同一病院の複数職種区分を含む）です。全国の全病院を自動発見する仕組みではありません。個別ページはURLを更新し、対象病院を増やすには設定へ追記してください。甲南会の採用一覧は同一ドメインの臨床工学技士募集リンクを最大6件まで発見します。

「掲載あり」は募集ページを取得し、臨床工学技士の募集に関する記載が見つかったことを示します。実際に応募できることを保証する表示ではありません。募集期限は表・定義リスト・見出しの明確な受付期間/締切欄から読み取ります。採用日や試験日を期限として使用しません。年のない日付、PDFのみ、複数回の異なる締切は推測せず「公式ページで確認」とします。HTML構造の変化により解析できない場合もあるため、応募前に公式募集要項をご確認ください。

初回収集では9件を取得、うち2件の期限経過を確認しました。国立病院機構 関東信越グループはrobots.txtの確認ができず、募集ページの取得を控えています。初回収集の日時・件数は `jobs.json` に記録しています。

## 収集方針

- robots.txtのアクセス制限、Crawl-delay、Request-rateに従います。
- robots.txtが404/410の場合のみ不在として扱います。他の取得失敗や403/429は対象ページを取得しません。
- 同一ホストへのアクセス間隔は最低3秒。1リクエスト25秒、最大2MB、1サイトの自動発見は最大6件。
- リダイレクトは自動追跡せず、URLと取得規則の確認が必要なエラーとして扱います。
- 認証、CAPTCHA、アクセス制限の回避は行いません。
- 本文やPDF全体を転載せず、病院名・募集ページ名・期限などの最低限の情報と公式リンクを掲載します。
- サイトの利用規約や運営者からの要望により取得停止が必要な場合は、設定から対象URLを除外してください。
- 削除/発見されなくなった募集は「要確認」として履歴を保持します。停止対象の情報を完全に取り下げる場合はJSONからも削除してください。

## ローカルで動作確認

Python 3.12以上:

```sh
python -m pip install -r requirements.txt
python -m unittest test_crawl
python crawl.py
python -m http.server 8000
```

http://localhost:8000/ を開きます。ファイルを直接開くとブラウザーがJSON読み込みを制限するため、HTTPサーバーを使ってください。

外部フォントはGoogle Fontsを利用し、取得できない場合は端末のフォントへ切り替えます。解析や広告、応募者の個人情報収集は行いません。

## 参考

- GitHub Pagesの公開設定: https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site
- GitHub Actionsの定期実行: https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule
