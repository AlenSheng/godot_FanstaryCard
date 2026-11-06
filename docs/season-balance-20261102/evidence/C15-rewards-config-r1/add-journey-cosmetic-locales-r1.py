from pathlib import Path
import json,hashlib

ids=['trail-seeker','relic-seeker','first-threshold','waymark-seal','veil-warden','veilbound-seal','fivefold-chronicle','convergent-sigil','veil-cartographer','relicbound-pathfinder']
data={
'en':[
('Trail Seeker','A bronze portrait frame with dim wayfinding runes.'),
('Relic Seeker','A title for those who seek forgotten relics.'),
('The First Threshold','A collection seal recording your first passage.'),
('Waymark Seal','A dark stone card back with an angular path seal.'),
('Veil Warden','A title marking watch over the Veil.'),
('Veilbound Seal','A silver portrait frame bearing the Veil seal.'),
('Fivefold Chronicle','A collection seal recording the five elements.'),
('Convergent Sigil','A card back uniting the five elemental signs.'),
('Veil Cartographer','A title for mapping paths through the Veil.'),
('Relicbound Pathfinder','An antique gold portrait frame with the complete path sigil.')],
'zh-CN':[
('寻迹者','青铜头像边框，嵌有微光寻途符纹。'),('遗迹寻者','授予探寻失落遗迹之人的身份称号。'),
('初越门槛','记载初次穿越门槛的收藏印记。'),('寻途之印','深色石纹卡背，饰有棱角分明的寻途符印。'),
('遗境守望','象征守望遗境的身份称号。'),('帷幕守印','银色头像边框，镶嵌帷幕符印。'),
('五行纪事','记载五行元素的收藏印记。'),('五行合契','汇合五行纹章的卡背。'),
('遗境绘图师','授予绘制遗境路径之人的身份称号。'),('遗境先行者','暗金头像边框，饰有完整寻途符印。')],
'es':[
('Buscador de sendas','Marco de retrato de bronce con tenues runas de orientación.'),('Buscador de reliquias','Título para quienes buscan reliquias olvidadas.'),
('El primer umbral','Sello de colección que recuerda tu primer paso.'),('Sello del camino','Reverso de piedra oscura con un sello angular del camino.'),
('Vigía del Velo','Título que simboliza la vigilancia del Velo.'),('Sello del Velo','Marco de retrato plateado con el sello del Velo.'),
('Crónica de los cinco','Sello de colección que representa los cinco elementos.'),('Sigilo convergente','Reverso que reúne los cinco signos elementales.'),
('Cartógrafo del Velo','Título para quienes trazan caminos por el Velo.'),('Pionero de Relicbound','Marco de oro envejecido con el sigilo completo del camino.')],
'fr':[
('Chercheur de pistes','Cadre de portrait en bronze aux discrètes runes de guidage.'),('Chercheur de reliques','Titre de ceux qui cherchent les reliques oubliées.'),
('Le premier seuil','Sceau de collection commémorant votre premier passage.'),('Sceau du chemin','Dos de carte en pierre sombre au sceau anguleux.'),
('Veilleur du Voile','Titre symbolisant la veille sur le Voile.'),('Sceau du Voile','Cadre de portrait argenté portant le sceau du Voile.'),
('Chronique des cinq','Sceau de collection représentant les cinq éléments.'),('Sigil de convergence','Dos de carte réunissant les cinq signes élémentaires.'),
('Cartographe du Voile','Titre de ceux qui tracent les voies du Voile.'),('Pionnier de Relicbound','Cadre en or patiné portant le sceau complet du chemin.')],
'pt':[
('Explorador de trilhas','Moldura de bronze com discretas runas de orientação.'),('Buscador de relíquias','Título para quem procura relíquias esquecidas.'),
('O primeiro limiar','Selo de coleção que registra sua primeira passagem.'),('Selo do caminho','Verso de pedra escura com um selo angular do caminho.'),
('Vigia do Véu','Título que simboliza a vigília sobre o Véu.'),('Selo do Véu','Moldura prateada com o selo do Véu.'),
('Crônica dos cinco','Selo de coleção que representa os cinco elementos.'),('Sigilo convergente','Verso que reúne os cinco símbolos elementais.'),
('Cartógrafo do Véu','Título para quem mapeia caminhos pelo Véu.'),('Pioneiro de Relicbound','Moldura de ouro envelhecido com o sigilo completo do caminho.')],
'id':[
('Penjejak Jalan','Bingkai potret perunggu dengan rune penunjuk jalan yang redup.'),('Pencari Relik','Gelar bagi pencari relik yang terlupakan.'),
('Ambang Pertama','Segel koleksi yang mencatat perlintasan pertamamu.'),('Segel Penunjuk','Bagian belakang kartu batu gelap dengan segel jalan bersudut.'),
('Pengawas Tabir','Gelar yang melambangkan penjagaan atas Tabir.'),('Segel Tabir','Bingkai potret perak dengan segel Tabir.'),
('Kronik Lima Unsur','Segel koleksi yang mencatat lima unsur.'),('Lambang Pertautan','Bagian belakang kartu yang menyatukan lima lambang unsur.'),
('Pemetaan Tabir','Gelar bagi pemeta jalan melintasi Tabir.'),('Perintis Relicbound','Bingkai emas antik dengan lambang jalan yang lengkap.')],
'ru':[
('Искатель следов','Бронзовая рамка портрета с тусклыми путевыми рунами.'),('Искатель реликвий','Титул для тех, кто ищет забытые реликвии.'),
('Первый порог','Коллекционная печать в память о первом переходе.'),('Печать пути','Рубашка из тёмного камня с угловатой печатью пути.'),
('Дозорный Завесы','Титул, символизирующий дозор у Завесы.'),('Печать Завесы','Серебряная рамка портрета с печатью Завесы.'),
('Летопись пяти стихий','Коллекционная печать пяти стихий.'),('Знак единения','Рубашка карты, объединяющая знаки пяти стихий.'),
('Картограф Завесы','Титул для тех, кто наносит на карту пути Завесы.'),('Первопроходец Relicbound','Рамка из старого золота с полной печатью пути.')],
'ja':[
('軌跡の探求者','淡い道標のルーンを刻んだ青銅の肖像フレーム。'),('遺物の探求者','忘れられた遺物を探す者の称号。'),
('最初の境界','初めて境界を越えた証を残す収集印。'),('道標の印','角張った道標の印を刻んだ暗い石のカード裏面。'),
('帳の見張り人','帳を見守る姿を象徴する称号。'),('帳の守印','帳の印をあしらった銀の肖像フレーム。'),
('五行の記録','五つの元素を記録する収集印。'),('五行の契印','五つの元素の紋章が集うカード裏面。'),
('帳の地図師','帳を通る道を描く者の称号。'),('Relicboundの先駆者','完全な道標の印をあしらった古金色の肖像フレーム。')],
'ko':[
('흔적 추적자','은은한 길잡이 룬을 새긴 청동 초상화 테두리.'),('유물 탐색자','잊힌 유물을 찾아 나서는 이의 칭호.'),
('첫 번째 문턱','처음 문턱을 넘은 순간을 기록하는 수집 인장.'),('길잡이 인장','각진 길잡이 인장을 새긴 어두운 돌무늬 카드 뒷면.'),
('장막의 파수꾼','장막을 지켜보는 이를 상징하는 칭호.'),('장막의 수호 인장','장막의 인장을 장식한 은빛 초상화 테두리.'),
('오행의 기록','다섯 원소를 기록하는 수집 인장.'),('오행의 결속','다섯 원소의 문양을 하나로 모은 카드 뒷면.'),
('장막의 지도 제작자','장막을 지나는 길을 그리는 이의 칭호.'),('Relicbound의 개척자','완전한 길잡이 인장을 장식한 고풍스러운 금빛 초상화 테두리.')],
'hi':[
('पथ अन्वेषक','मंद पथदर्शी चिह्नों वाला कांस्य चित्र फ़्रेम।'),('अवशेष अन्वेषक','भूले हुए अवशेष खोजने वालों की उपाधि।'),
('पहली दहलीज़','आपकी पहली यात्रा को दर्ज करने वाली संग्रह मुहर।'),('पथ की मुहर','कोणीय पथ मुहर वाला गहरे पत्थर का कार्ड पृष्ठभाग।'),
('आवरण का प्रहरी','आवरण पर निगरानी का प्रतीक उपाधि।'),('आवरण की मुहर','आवरण की मुहर वाला चाँदी का चित्र फ़्रेम।'),
('पंचतत्त्व गाथा','पाँच तत्त्वों को दर्ज करने वाली संग्रह मुहर।'),('संगम चिह्न','पाँच तत्त्वों के चिह्नों को जोड़ने वाला कार्ड पृष्ठभाग।'),
('आवरण का मानचित्रकार','आवरण के मार्गों का मानचित्र बनाने वालों की उपाधि।'),('Relicbound पथप्रदर्शक','पूर्ण पथ चिह्न वाला पुरातन स्वर्ण चित्र फ़्रेम।')],
'ar':[
('متتبّع الآثار','إطار صورة برونزي بنقوش خافتة تدلّ على الطريق.'),('باحث الآثار','لقب لمن يبحثون عن الآثار المنسية.'),
('العتبة الأولى','ختم مقتنيات يوثّق عبورك الأول.'),('ختم الدرب','ظهر بطاقة من الحجر الداكن يحمل ختم درب زاويًّا.'),
('حارس الحجاب','لقب يرمز إلى السهر على الحجاب.'),('ختم الحجاب','إطار صورة فضي يحمل ختم الحجاب.'),
('سجلّ العناصر الخمسة','ختم مقتنيات يوثّق العناصر الخمسة.'),('رمز التلاقي','ظهر بطاقة يجمع رموز العناصر الخمسة.'),
('رسّام خرائط الحجاب','لقب لمن يرسمون الدروب عبر الحجاب.'),('رائد Relicbound','إطار صورة من الذهب المعتّق يحمل رمز الدرب الكامل.')]
}
repo=Path.cwd();changes={}
for code,rows in data.items():
    assert len(rows)==len(ids)
    path=repo/'client/data/locales'/f'{code}.json';original=json.loads(path.read_text('utf-8'));updated=json.loads(path.read_text('utf-8'))
    added={}
    for identifier,(name,description) in zip(ids,rows):
        for suffix,value in [('name',name),('description',description)]:
            key=f'journey_cosmetic_{identifier.replace("-","_")}_{suffix}'
            assert key not in updated['strings'];updated['strings'][key]=value;added[key]=value
    for key,value in original.items():
        if key!='strings':assert updated[key]==value
    assert all(updated['strings'][key]==value for key,value in original['strings'].items())
    path.write_text(json.dumps(updated,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    changes[code]={'added':added,'original_values_unchanged':True,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
out=Path(r'G:\PR13Evidence\season-balance-20261102-r1\journey-cosmetic-localization-changes.original.json');assert not out.exists();out.write_text(json.dumps(changes,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Added 20 names/descriptions to each of 11 locale packs; all prior values preserved.')
