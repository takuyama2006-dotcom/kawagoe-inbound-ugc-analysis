"""Descriptive analysis of saved YouTube snapshots, without third-party dependencies."""
import argparse
from collections import Counter
import datetime as dt
import html
import json
from pathlib import Path
import re
import statistics as st
import unicodedata

BASE=Path(__file__).resolve().parent
LABEL={'ja':'日本語','zh':'中国語','en':'英語','ko':'韓国語'}
# Fixed before loading statistics. Themes may overlap.
TERMS={
 '食・グルメ':{'ja':['グルメ','食べ歩き','食べ放題','ランチ'],'zh':['美食','小吃','餐廳','餐厅','吃'],'en':['food','street food','restaurant'],'ko':['맛집','미식','먹거리','먹방','음식']},
 'サツマイモ':{'ja':['さつまいも','サツマイモ','薩摩芋','芋'],'zh':['地瓜','紅薯','红薯','甘薯','甜薯'],'en':['sweet potato','sweet potatoes'],'ko':['고구마']},
 'スイーツ':{'ja':['スイーツ','デザート','菓子','プリン'],'zh':['甜點','甜点','甜品','糖果'],'en':['sweets','dessert','candy','pudding'],'ko':['디저트','후식','과자','스위츠']},
 '日帰り':{'ja':['日帰り','一日旅','1日旅'],'zh':['一日遊','一日游','当天往返','當天來回'],'en':['day trip','daytrip','day tour'],'ko':['당일치기','당일 여행','당일여행','반일']},
 '東京':{'ja':['東京'],'zh':['東京','东京'],'en':['tokyo'],'ko':['도쿄','동경']},
 '江戸・歴史':{'ja':['江戸','歴史','レトロ'],'zh':['江戶','江户','歷史','历史','復古'],'en':['edo','historic','history','retro','old town'],'ko':['에도','역사','레트로']},
 '神社':{'ja':['神社'],'zh':['神社'],'en':['shrine'],'ko':['신사']},
 '寺':{'ja':['喜多院','寺院','お寺'],'zh':['喜多院','寺廟','寺庙'],'en':['temple'],'ko':['사찰','절','기타인']},
 '着物':{'ja':['着物','きもの'],'zh':['和服','浴衣'],'en':['kimono','yukata'],'ko':['기모노','유카타']},
 '祭り':{'ja':['祭り','まつり','祭礼'],'zh':['祭典','祭祀','川越祭','川越祭典'],'en':['festival','matsuri'],'ko':['축제','마츠리']},
 'カフェ':{'ja':['カフェ','喫茶','珈琲'],'zh':['咖啡'],'en':['cafe','café','coffee'],'ko':['카페','커피']},
 '交通・アクセス':{'ja':['アクセス','行き方','電車','駅から'],'zh':['交通','怎麼去','怎么去','電車','电车'],'en':['how to get','train','access'],'ko':['가는 법','가는법','전철','교통']}
}

def norm(s):return unicodedata.normalize('NFKC',html.unescape(s or '')).casefold()
def matched(text,terms,lang):
    text=norm(text)
    for term in terms:
        term=norm(term)
        if lang=='en':
            if re.search(r'(?<![a-z])'+re.escape(term)+r'(?![a-z])',text):return True
        elif term in text:return True
    return False

def proxy(title):
    title=html.unescape(title)
    kana=len(re.findall(r'[ぁ-ゖァ-ヺ]',title))
    hangul=len(re.findall(r'[가-힣]',title))
    han=len(re.findall(r'[一-鿿]',title))
    latin=len(re.findall(r'[A-Za-z]',title))
    if hangul>=4:return 'ko'
    if kana>=4:return 'ja'
    if han>=6 and kana==0 and hangul==0:return 'zh'
    if latin>=15 and kana==0 and hangul==0 and han<6:return 'en'
    return 'uncertain'

def avg(xs):return st.mean(xs) if xs else None
def median(xs):return st.median(xs) if xs else None
def metric(rows):
    vs=[r['views'] for r in rows if r['views'] is not None]
    rates={}
    for field in ['likes','comments']:
        valid=[r for r in rows if r['views'] is not None and r['views']>0 and r[field] is not None]
        rates[field+'_mean_pct']=avg([r[field]/r['views']*100 for r in valid])
        rates[field+'_pooled_pct']=sum(r[field] for r in valid)/sum(r['views'] for r in valid)*100 if valid else None
        rates[field+'_valid_n']=len(valid)
    channels=Counter()
    for r in rows:channels[r['channel_id']]+=r['views'] or 0
    total=sum(vs)
    cutoff=dt.datetime(2025,11,6,tzinfo=dt.timezone.utc)
    recent=[r for r in rows if dt.datetime.fromisoformat(r['published'].replace('Z','+00:00'))>=cutoff]
    return {'n':len(rows),'views_valid_n':len(vs),'views_mean':avg(vs),'views_median':median(vs),
            'views_total':total,'views_mean_without_largest':avg(sorted(vs)[:-1]),
            'top1_view_share_pct':max(vs)/total*100 if total else None,
            'top_channel_view_share_pct':max(channels.values())/total*100 if total else None,
            'channels_n':len(channels),'recent_n':len(recent),
            'recent_views_median':median([r['views'] for r in recent if r['views'] is not None]),**rates}

def fmt(v,d=1):return '—' if v is None else f'{v:,.{d}f}'
def mdtable(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+['| '+' | '.join(str(x).replace('|','／').replace('\n',' ') for x in row)+' |' for row in rows])+'\n'

def analyze(folder):
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    if manifest['status']!='complete':raise ValueError('Snapshot incomplete')
    raw=json.loads((folder/'videos.json').read_text(encoding='utf-8'))
    members=json.loads((folder/'memberships.json').read_text(encoding='utf-8'))
    rows={}
    for v in raw:
        sn=v['snippet'];ss=v.get('statistics',{})
        rows[v['id']]={'id':v['id'],'title':html.unescape(sn['title']),'description':sn.get('description',''),
                       'tags':sn.get('tags',[]),'published':sn['publishedAt'],
                       'channel_id':sn['channelId'],'channel':sn['channelTitle'],
                       'declared_language':sn.get('defaultAudioLanguage',sn.get('defaultLanguage','unknown')),
                       'title_proxy':proxy(sn['title']),
                       **{key:int(ss[api]) if api in ss else None for key,api in [('views','viewCount'),('likes','likeCount'),('comments','commentCount')]}}
    groups={lang:[rows[vid] for vid in sorted({m['video_id'] for m in members if m['search_language']==lang}) if vid in rows] for lang in LABEL}
    def local(r):
        text=norm(r['title']+' '+r['description']+' '+' '.join(r['tags']))
        return any(x in text for x in ['川越','kawagoe','가와고에','카와고에'])
    screened={lang:[r for r in rs if r['title_proxy']==lang and local(r)] for lang,rs in groups.items()}
    results={'search':{},'title_proxy':{},'overlap':{},'keywords':{}}
    for lang in LABEL:
        results['search'][lang]=metric(groups[lang]);results['title_proxy'][lang]=metric(screened[lang])
        for other in LABEL:
            results['overlap'][lang+'_'+other]=len({r['id'] for r in groups[lang]}&{r['id'] for r in groups[other]})
        results['keywords'][lang]={}
        for theme,terms in TERMS.items():
            hit=[r for r in screened[lang] if matched(r['title']+' '+r['description']+' '+' '.join(r['tags']),terms[lang],lang)]
            ids={r['id'] for r in hit};rest=[r for r in screened[lang] if r['id'] not in ids]
            results['keywords'][lang][theme]={'matched':metric(hit),'not_matched':metric(rest),'ids':sorted(ids)}
            assert len(hit)<=len(screened[lang])
    output=BASE/'results'/folder.name;output.mkdir(parents=True,exist_ok=True)
    for name,data in [('analysis.json',results),('video_review.json',list(rows.values())),('keyword_dictionary.json',TERMS)]:
        (output/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    report='# 川越YouTube UGC再分析\n\n取得日：2026年11月6日（日本時間）。YouTube Data APIの新規取得データから集計。\n\n'
    report+='## 調査設計\n\n日本語・中国語・英語・韓国語の検索を各最大10ページ実施。関連度順、旅行・イベントカテゴリ19、地域・公開期間は制限なし。動画ID単位で重複を排除し、言語間の重複は別途計数しました。視聴者の国籍・言語は取得していません。\n\n'
    report+=f'検索集合の延べ本数は{sum(len(g) for g in groups.values()):,}件、統計取得済みのユニーク動画は{len(rows):,}件。検索後に統計を取得できなかった動画は{len(manifest["unavailable_ids"])}件です。\n\n'
    report+='## 1. 検索集合全体\n\nこの表は「指定言語で検索した集合」であり、動画言語・視聴者言語ごとの結果ではありません。\n\n'
    def summary_table(kind):
        return mdtable(['検索設定','本数','平均再生','中央値','平均高評価率%','合計ベース高評価率%','平均コメント率%'],[[LABEL[l],m['n'],fmt(m['views_mean']),fmt(m['views_median']),fmt(m['likes_mean_pct'],2),fmt(m['likes_pooled_pct'],2),fmt(m['comments_mean_pct'],2)] for l,m in results[kind].items()])
    report+=summary_table('search')
    report+='\n### 検索集合間の重複本数\n\n'+mdtable(['設定']+list(LABEL.values()),[[LABEL[l]]+[results['overlap'][l+'_'+o] for o in LABEL] for l in LABEL])
    report+='\n## 2. 言語混入の点検\n\nタイトル文字種の簡易規則でスクリーニングしました。ハングル4字以上→韓国語、かな4字以上→日本語、漢字6字以上かつかな・ハングルなし→中国語、ラテン文字15字以上かつかな・ハングルなし・漢字6字未満→英語、それ以外→判定保留です。実際の音声・字幕・視聴者言語の判定ではありません。混在タイトルも誤分類し得ます。\n\n'
    report+=mdtable(['検索設定','日本語候補','中国語候補','英語候補','韓国語候補','保留'],[[LABEL[l]]+[sum(r['title_proxy']==k for r in groups[l]) for k in ['ja','zh','en','ko','uncertain']] for l in LABEL])
    report+='\n## 3. タイトル文字種と川越表記で絞った参考集合\n\nタイトル文字種が検索設定と一致し、タイトル・説明文・タグに「川越 / kawagoe / 가와고에 / 카와고에」のいずれかを含む動画に限定しました。川越への実訪問を確認した分類ではありません。該当しない動画の除外本数は、文字種一致本数と下表の差です。厳密な言語比較ではなく、混入の影響を見る感度分析です。公式・企業投稿を除外していないため、以下も個人UGC限定の結果ではありません。\n\n'+summary_table('title_proxy')
    report+='\n### 外れ値・投稿時期・チャンネル集中\n\n'+mdtable(['設定','最大動画の再生占有率%','最大チャンネル占有率%','最大動画除外後平均','2025/11/6以降投稿本数','同期間の再生中央値'],[[LABEL[l],fmt(m['top1_view_share_pct']),fmt(m['top_channel_view_share_pct']),fmt(m['views_mean_without_largest']),m['recent_n'],fmt(m['recent_views_median'])] for l,m in results['title_proxy'].items()])
    report+='\n直近期間の動画も露出期間はそろっていません。「投稿日以降の累積再生」であり、年ごとの市場成長率を示しません。\n\n## 4. テーマ別の参考集計\n\nタイトル・説明文・タグに検索語を含む動画をOR条件で抽出。NFKC正規化・英語大小文字統一・英語単語境界を使用。辞書は `keyword_dictionary.json` に保存。テーマは重複します。比較対象は同じ参考集合内の非該当動画です。n<10は少数として扱い、順位だけで施策を決めません。説明文には定型タグもあるため、内容自体の検証には視聴が必要です。\n\n'
    for lang in LABEL:
        report+='### '+LABEL[lang]+'\n\n'
        report+=mdtable(['テーマ','該当本数','平均再生','中央値','非該当中央値','平均高評価率%','平均コメント率%','件数注意'],[[t,m['matched']['n'],fmt(m['matched']['views_mean']),fmt(m['matched']['views_median']),fmt(m['not_matched']['views_median']),fmt(m['matched']['likes_mean_pct'],2),fmt(m['matched']['comments_mean_pct'],2),'少数' if m['matched']['n']<10 else ''] for t,m in results['keywords'][lang].items()])+'\n'
    report+='## 5. データ品質と解釈上の制約\n\n'
    report+=mdtable(['項目','件数（ユニーク動画）'],[['再生回数欠損',sum(r['views'] is None for r in rows.values())],['再生回数0',sum(r['views']==0 for r in rows.values())],['高評価数欠損',sum(r['likes'] is None for r in rows.values())],['コメント数欠損',sum(r['comments'] is None for r in rows.values())]])
    report+='\n- 欠損をゼロに置換しません。率は再生数>0かつ分子が取得できた動画で算出します。率の有効本数はanalysis.jsonに保存しています。\n- 平均率は動画別率の単純平均。合計ベース率は有効動画の分子合計÷再生合計で、別指標です。\n- 視聴者属性、予約、来訪、消費額、コメント本文は取得していません。コメントの多さを好意・需要とは断定できません。\n- 検索順位、投稿後経過時間、動画長、Shorts、チャンネル規模を調整した因果分析ではありません。\n- 検索カテゴリを19に限定しており、他カテゴリの川越動画を網羅しません。\n- 元資料とは取得時点・地域設定・辞書が異なり、過去からの増減を示す比較には使用しません。\n- 全動画の目視・音声確認やUGC／公式投稿分類は未完了。施策は探索的仮説として扱います。\n\n## 6. 確認用の上位動画\n\n各参考集合の再生数上位5件。個別動画の確認先です。\n\n'
    for lang in LABEL:
        report+='### '+LABEL[lang]+'\n\n'
        for r in sorted(screened[lang],key=lambda r:r['views'] or 0,reverse=True)[:5]:
            title=r['title'].replace('[','（').replace(']','）').replace('\n',' ')
            report+=f'- [{title}](https://www.youtube.com/watch?v={r["id"]})：{fmt(r["views"],0)}回 / {r["channel"]} / {r["published"][:10]}\n'
        report+='\n'
    report+='## 再現と出典\n\n取得条件・API応答・SHA-256は対応するrunsフォルダのmanifest.jsonと原データに保存。分析コードはanalyze.py。APIキーは含みません。\n\n[YouTube search.list仕様](https://developers.google.com/youtube/data/reference/rest/v3/search/list) / [videos.list仕様](https://developers.google.com/youtube/data/reference/rest/v3/videos/list)\n'
    (output/'REPORT.md').write_text(report,encoding='utf-8')
    print(json.dumps({'snapshot':folder.name,'search':results['search'],'screened':results['title_proxy'],'output':str(output)},ensure_ascii=False,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('snapshot',type=Path);a=p.parse_args();analyze(a.snapshot)
