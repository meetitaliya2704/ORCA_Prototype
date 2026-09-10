from __future__ import annotations

from typing import Any
from app.schemas.assistant import AssistantIntent, AssistantLanguage

def detect_language(message: str, preferred: AssistantLanguage | str) -> str:
    pref_str = preferred.value if isinstance(preferred, AssistantLanguage) else str(preferred)
    if pref_str and pref_str != 'en':
        return pref_str
    for ch in message:
        code = ord(ch)
        if 0x0A80 <= code <= 0x0AFF:
            return 'gu'
        if 0x0B80 <= code <= 0x0BFF:
            return 'ta'
        if 0x0C00 <= code <= 0x0C7F:
            return 'te'
        if 0x0D00 <= code <= 0x0D7F:
            return 'ml'
        if 0x0980 <= code <= 0x09FF:
            return 'bn'
        if 0x0900 <= code <= 0x097F:
            if any(w in message for w in ['आहे', 'कशी', 'सांगा', 'माहिती', 'जवळचे', 'लाटा']):
                return 'mr'
            return 'hi'
    return 'en'

def format_land_notice(lang: str, latitude: float, longitude: float, nearest_coast: str, distance_km: float) -> str:
    if lang == 'hi':
        return (
            f'आपका अनुरोधित स्थान ({latitude:.4f}°N, {longitude:.4f}°E) ज़मीन पर (अंतर्देशीय) है, '
            f'जो निकटतम तट ({nearest_coast}) से लगभग {distance_km:.0f} किमी दूर है।\n\n'
            'समुद्री लहरों की ऊंचाई, समुद्र स्तर, समुद्री ज्वार-भाटा, समुद्री धाराएं और समुद्री सतह का तापमान (SST) '
            'केवल तटीय और खुले समुद्री जल में होते हैं, इसलिए इस अंतर्देशीय स्थान पर कोई समुद्री अवलोकन सेल उपलब्ध नहीं है।\n\n'
            f'समुद्री स्थिति या मछली पकड़ने के क्षेत्र (PFZ) की सलाह देखने के लिए कृपया {nearest_coast} के पास का कोई तटीय या समुद्री स्थान चुनें।'
        )
    if lang == 'gu':
        return (
            f'તમારું વિનંતી કરેલ સ્થાન ({latitude:.4f}°N, {longitude:.4f}°E) જમીન પર આવેલું છે, '
            f'જે નજીકના દરિયાકાંઠા ({nearest_coast}) થી આશરે {distance_km:.0f} કિમી દૂર છે。\n\n'
            'સમુદ્રી તરંગોની ઊંચાઈ, દરિયાઈ સપાટી, ભરતી-ઓટ, દરિયાઈ પ્રવાહો અને દરિયાઈ સપાટીનું તાપમાન (SST) '
            'ફક્ત દરિયાઈ પાણીમાં જ હોય છે, તેથી આ જમીની સ્થાને કોઈ દરિયાઈ અવલોકન સેલ ઉપલબ્ધ નથી。\n\n'
            f'દરિયાઈ સ્થિતિ અથવા સંભવિત મત્સ્યોદ્યોગ ક્ષેત્ર (PFZ) સલાહ જોવા માટે કૃપા કરીને {nearest_coast} નજીકનું કોઈ દરિયાકાંઠાનું કે સમુદ્રી સ્થાન પસંદ કરો。'
        )
    if lang == 'mr':
        return (
            f'आपले विनंती केलेले स्थान ({latitude:.4f}°N, {longitude:.4f}°E) जमिनीवर (अंतर्देशीय) आहे, '
            f'जे जवळच्या किनाऱ्यापासून ({nearest_coast}) सुमारे {distance_km:.0f} किमी अंतरावर आहे।\n\n'
            'समुद्राच्या लाटांची उंची, समुद्र पातळी, भरती-ओहोटी, सागरी प्रवाह आणि समुद्राच्या पृष्ठभागाचे तापमान (SST) '
            'केवळ किनारपट्टी आणि समुद्राच्या पाण्यात अस्तित्वात असतात, त्यामुळे या अंतर्देशीय स्थानावर कोणतेही सागरी निरीक्षण उपलब्ध नाही।\n\n'
            f'सागरी स्थिती किंवा संभाव्य मासेमारी क्षेत्र (PFZ) सल्ला पाहण्यासाठी कृपया {nearest_coast} जवळील किनारी किंवा सागरी स्थान निवडा।'
        )
    if lang == 'ta':
        return (
            f'நீங்கள் கோரிய இடம் ({latitude:.4f}°N, {longitude:.4f}°E) நிலப்பரப்பில் உள்ளது, '
            f'இது அருகிலுள்ள கடற்கரையிலிருந்து ({nearest_coast}) சுமார் {distance_km:.0f} கி.மீ தொலைவில் உள்ளது.\n\n'
            'கடல் அலை உயரம், கடல் மட்டம், அலை ஏற்ற இறக்கம், கடல் நீரோட்டம் மற்றும் கடல் மேற்பரப்பு வெப்பநிலை (SST) '
            'ஆகியவை கடற்பரப்பில் மட்டுமே அளவிடப்படும். எனவே இந்த நிலப்பரப்பில் கடல் கண்காணிப்பு தரவு கிடைக்கவில்லை.\n\n'
            f'கடல் நிலை அல்லது மீன்பிடி மண்டல (PFZ) ஆலோசனையைப் பெற, {nearest_coast} அருகிலுள்ள கடலோர இடத்தை தேர்ந்தெடுக்கவும்.'
        )
    if lang == 'te':
        return (
            f'మీరు అభ్యర్థించిన ప్రదేశం ({latitude:.4f}°N, {longitude:.4f}°E) భూభాగంలో ఉంది, '
            f'ఇది సమీప తీరానికి ({nearest_coast}) సుమారు {distance_km:.0f} కి.మీ దూరంలో ఉంది.\n\n'
            'సముద్రపు అలల ఎత్తు, సముద్ర మట్టం, పోటుపాటు, సముద్ర ప్రవాహాలు మరియు సముద్ర ఉపరితల ఉష్ణోగ్రత (SST) '
            'కేవలం సముద్ర జలాల్లో మాత్రమే ఉంటాయి, కాబట్టి ఈ భూభాగంలో సముద్ర పరిశీలన అందుబాటులో లేదు.\n\n'
            f'సముద్ర పరిస్థితులు లేదా చేపల వేట జోన్ (PFZ) సలహాలను వీక్షించడానికి, దయచేసి {nearest_coast} సమీపంలోని తీరప్రాంతాన్ని ఎంచుకోండి.'
        )
    if lang == 'ml':
        return (
            f'നിങ്ങൾ തിരഞ്ഞ സ്ഥാനം ({latitude:.4f}°N, {longitude:.4f}°E) കരയിലാണ്, '
            f'അടുത്തുള്ള തീരത്തുനിന്ന് ({nearest_coast}) ഏകദേശം {distance_km:.0f} കി.മീ അകലെയാണ്.\n\n'
            'സമുദ്ര തിരമാല ഉയരം, വേലിയേറ്റം, സമുദ്ര പ്രവാഹങ്ങൾ, സമുദ്രോപരിതല താപനില (SST) '
            'എന്നിവ സമുദ്രജലത്തിൽ മാത്രമേ ഉണ്ടാകൂ. അതിനാൽ കരയിൽ സമുദ്ര നിരീക്ഷണ വിവരങ്ങൾ ലഭ്യമല്ല.\n\n'
            f'സമുദ്ര സാഹചര്യങ്ങളോ മത്സ്യബന്ധന മേഖല (PFZ) വിവരങ്ങളോ കാണാൻ {nearest_coast} അടുത്തുള്ള ഒരു തീരപ്രദേശം തിരഞ്ഞെടുക്കുക.'
        )
    if lang == 'bn':
        return (
            f'আপনার অনুরোধকৃত অবস্থান ({latitude:.4f}°N, {longitude:.4f}°E) ভূমির অভ্যন্তরে অবস্থিত, '
            f'যা নিকটতম উপকূল ({nearest_coast}) থেকে প্রায় {distance_km:.0f} কিমি দূরে।\n\n'
            'সমুদ্রের ঢেউয়ের উচ্চতা, জোয়ার-ভাটা, সমুদ্রস্রোত এবং সমুদ্রপৃষ্ঠের তাপমাত্রা (SST) '
            'শুধুমাত্র উপকূলীয় ও সমুদ্রের পানিতে বিদ্যমান, তাই এই স্থলভাগে কোনো সামুদ্রিক পর্যবেক্ষণ উপলব্ধ নেই।\n\n'
            f'সামুদ্রিক পরিস্থিতি বা সম্ভাব্য মাছ ধরার এলাকা (PFZ) দেখতে অনুগ্রহ করে {nearest_coast}-এর কাছাকাছি একটি উপকূলীয় অবস্থান নির্বাচন করুন।'
        )
    return (
        f'Your query location ({latitude:.4f}°N, {longitude:.4f}°E) is inland on land, '
        f'approximately {distance_km:.0f} km from the nearest coast ({nearest_coast}).\n\n'
        'Ocean wave heights, sea level anomalies, ocean tides, ocean currents, and Sea Surface Temperature (SST) '
        'are maritime parameters that only exist in coastal and offshore waters, so no marine observation cells '
        'are available at this inland position.\n\n'
        f'To view marine conditions or fishing zone advisories, select or enter a coastal or offshore location near {nearest_coast}.'
    )

def format_inland_prefix_for_pfz(lang: str, coast_dist: float, nearest_coast: str, landing_centre: str) -> str:
    if lang == 'hi':
        return (
            f'सूचना: आपका अनुरोधित स्थान अंतर्देशीय है ({nearest_coast} से {coast_dist:.0f} किमी दूर)। '
            f'निकटतम अपतटीय संभावित मछली पकड़ने का क्षेत्र (PFZ) {landing_centre} के पास स्थित है:\n\n'
        )
    if lang == 'gu':
        return (
            f'નોંધ: તમારું વિનંતી કરેલ સ્થાન જમીન પર છે ({nearest_coast} થી {coast_dist:.0f} કિમી દૂર). '
            f'સૌથી નજીકનું દરિયાઈ સંભવિત મત્સ્યોદ્યોગ ક્ષેત્ર (PFZ) {landing_centre} પાસે આવેલું છે:\n\n'
        )
    if lang == 'mr':
        return (
            f'टीप: आपले स्थान जमिनीवर आहे ({nearest_coast} पासून {coast_dist:.0f} किमी). '
            f'सर्वात जवळचे सागरी संभाव्य मासेमारी क्षेत्र (PFZ) {landing_centre} जवळ स्थित आहे:\n\n'
        )
    if lang == 'ta':
        return (
            f'குறிப்பு: நீங்கள் கோரிய இடம் நிலப்பரப்பில் உள்ளது ({nearest_coast}-லிருந்து {coast_dist:.0f} கி.மீ). '
            f'அருகிலுள்ள கடல் மீன்பிடி மண்டலம் (PFZ) {landing_centre} அருகில் அமைந்துள்ளது:\n\n'
        )
    if lang == 'te':
        return (
            f'గమనిక: మీ ప్రదేశం భూభాగంలో ఉంది ({nearest_coast} నుండి {coast_dist:.0f} కి.మీ). '
            f'సమీప సముద్ర చేపల వేట జోన్ (PFZ) {landing_centre} సమీపంలో ఉంది:\n\n'
        )
    if lang == 'ml':
        return (
            f'ശ്രദ്ധിക്കുക: നിങ്ങളുടെ സ്ഥാനം കരയിലാണ് ({nearest_coast}-ൽ നിന്ന് {coast_dist:.0f} കി.മീ). '
            f'ഏറ്റവും അടുത്തുള്ള സമുദ്ര മത്സ്യബന്ധന മേഖല (PFZ) {landing_centre}-ന് സമീപമാണ്:\n\n'
        )
    if lang == 'bn':
        return (
            f'নোট: আপনার অনুরোধকৃত অবস্থান স্থলের অভ্যন্তরে ({nearest_coast} থেকে {coast_dist:.0f} কিমি)। '
            f'নিকটতম উপকূলবর্তী সম্ভাব্য মাছ ধরার এলাকা (PFZ) {landing_centre}-এর কাছে অবস্থিত:\n\n'
        )
    return (
        f'Note: Your query position is inland ({coast_dist:.0f} km from {nearest_coast}). '
        f'The nearest offshore Potential Fishing Zone advisory is located off {landing_centre}:\n\n'
    )

def format_pfz_bulletin(
    lang: str,
    landing_centre: str,
    direction: str,
    bearing_deg: float,
    dist_coast_str: str,
    depth_str: str,
    lat_dms: str,
    lat_num: float,
    lon_dms: str,
    lon_num: float,
    sector_code: str,
    region_name: str,
    distance_km: float,
    date_str: str,
    land_prefix: str = '',
) -> str:
    if lang == 'hi':
        return (
            f'{land_prefix}'
            f'आधिकारिक इनकॉइस (INCOIS) पीएफजेड (PFZ) सलाह विवरण:\n'
            f'• उतरने का केंद्र (Landing Centre): {landing_centre}\n'
            f'• दिशा (Direction): {direction}\n'
            f'• बेयरिंग कोण (Bearing): {bearing_deg:.0f}°\n'
            f'• तट से दूरी (कि.मी.): {dist_coast_str}\n'
            f'• गहराई (मीटर): {depth_str}\n'
            f'• अक्षांश (Latitude): {lat_dms} ({lat_num:.4f}°)\n'
            f'• देशांतर (Longitude): {lon_dms} ({lon_num:.4f}°)\n'
            f'• सेक्टर एवं क्षेत्र: Sector {sector_code} ({region_name})\n'
            f'• आपकी स्थिति से दूरी: {distance_km:.1f} किमी दूर\n'
            f'• सलाह की वैधता: {date_str} तक वैध\n\n'
            'पीएफजेड सलाह समुद्र की उन विशेषताओं (एसएसटी और क्लोरोफिल सीमा) की पहचान करती है जहां मछलियां इकट्ठा होती हैं। '
            'प्रस्थान करने से पहले हमेशा स्थानीय समुद्री सुरक्षा सलाह अवश्य जांचें।'
        )
    if lang == 'gu':
        return (
            f'{land_prefix}'
            f'સત્તાવાર ઇનકોઇસ (INCOIS) પીએફઝેડ (PFZ) સલાહ વિગતો:\n'
            f'• ઉતરાણ કેન્દ્ર (Landing Centre): {landing_centre}\n'
            f'• દિશા (Direction): {direction}\n'
            f'• બેયરિંગ કોણ (Bearing): {bearing_deg:.0f}°\n'
            f'• કાંઠાથી અંતર (કિમી): {dist_coast_str}\n'
            f'• ઊંડાઈ (મીટર): {depth_str}\n'
            f'• અક્ષાંશ (Latitude): {lat_dms} ({lat_num:.4f}°)\n'
            f'• રેખાંશ (Longitude): {lon_dms} ({lon_num:.4f}°)\n'
            f'• સેક્ટર અને પ્રદેશ: Sector {sector_code} ({region_name})\n'
            f'• તમારા સ્થાનથી અંતર: {distance_km:.1f} કિમી દૂર\n'
            f'• સલાહની માન્યતા: {date_str} સુધી માન્ય\n\n'
            'પીએફઝેડ સલાહ દરિયાઈ પરિસ્થિતિઓ (એસએસટી ફ્રન્ટ્સ અને ક્લોરોફિલ બાઉન્ડ્રી) દર્શાવે છે જ્યાં માછલીઓ એકત્રિત થવાની સંભાવના વધુ હોય છે। '
            'દરિયામાં જતાં પહેલાં હંમેશાં સ્થાનિક દરિયાઈ સુરક્ષા સ્થિતિની ખાતરી કરો।'
        )
    if lang == 'mr':
        return (
            f'{land_prefix}'
            f'अधिकृत इनकॉइस (INCOIS) पीएफझेड (PFZ) सल्लागार तपशील:\n'
            f'• लँडिंग केंद्र (Landing Centre): {landing_centre}\n'
            f'• दिशा (Direction): {direction}\n'
            f'• बेअरिंग (Bearing): {bearing_deg:.0f}°\n'
            f'• किनाऱ्यापासून अंतर (किमी): {dist_coast_str}\n'
            f'• खोली (मीटर): {depth_str}\n'
            f'• अक्षांश (Latitude): {lat_dms} ({lat_num:.4f}°)\n'
            f'• रेखांश (Longitude): {lon_dms} ({lon_num:.4f}°)\n'
            f'• सेक्टर आणि प्रदेश: Sector {sector_code} ({region_name})\n'
            f'• स्थानापासून अंतर: {distance_km:.1f} किमी अंतरावर\n'
            f'• सल्ला वैधता: {date_str} पर्यंत वैध\n\n'
            'पीएफझेड सल्लागार सागरी वैशिष्ट्ये (एसएसटी आणि क्लोरोफिल) दर्शवतात जेथे मासे गोळा होतात। '
            'प्रवासास निघण्यापूर्वी नेहमी स्थानिक समुद्र सुरक्षिततेची पडताळणी करा।'
        )
    if lang == 'ta':
        return (
            f'{land_prefix}'
            f'அதிகாரப்பூர்வ இன்கோயிஸ் (INCOIS) பி.எஃப்.இசட் (PFZ) ஆலோசனை விவரங்கள்:\n'
            f'• இறங்கும் மையம் (Landing Centre): {landing_centre}\n'
            f'• திசை (Direction): {direction}\n'
            f'• திசைக் கோணம் (Bearing): {bearing_deg:.0f}°\n'
            f'• கரையிலிருந்து தூரம் (கி.மீ): {dist_coast_str}\n'
            f'• ஆழம் (மீட்டர்): {depth_str}\n'
            f'• அட்சரேகை (Latitude): {lat_dms} ({lat_num:.4f}°)\n'
            f'• தீர்க்கரேகை (Longitude): {lon_dms} ({lon_num:.4f}°)\n'
            f'• துறை & மண்டலம்: Sector {sector_code} ({region_name})\n'
            f'• உங்கள் தூரம்: {distance_km:.1f} கி.மீ தொலைவில்\n'
            f'• செல்லுபடியாகும் காலம்: {date_str} வரை\n\n'
            'பி.எஃப்.இசட் ஆலோசனைகள் மீன்கள் அதிகமாகக் கூடும் கடல் அம்சங்களை அடையாளம் காட்டுகின்றன। '
            'கடலுக்குச் செல்வதற்கு முன் எப்போதும் அதிகாரப்பூர்வ வானிலை பாதுகாப்பு எச்சரிக்கைகளைச் சரிபார்க்கவும்।'
        )
    if lang == 'te':
        return (
            f'{land_prefix}'
            f'అధికారిక ఇన్‌కాయిస్ (INCOIS) పి.ఎఫ్.జెడ్ (PFZ) సలహా వివరాలు:\n'
            f'• లాండింగ్ కేంద్రం (Landing Centre): {landing_centre}\n'
            f'• దిశ (Direction): {direction}\n'
            f'• బేరింగ్ (Bearing): {bearing_deg:.0f}°\n'
            f'• తీరం నుండి దూరం (కి.మీ): {dist_coast_str}\n'
            f'• లోతు (మీటర్లు): {depth_str}\n'
            f'• అక్షాంశం (Latitude): {lat_dms} ({lat_num:.4f}°)\n'
            f'• రేఖాంశం (Longitude): {lon_dms} ({lon_num:.4f}°)\n'
            f'• సెక్టార్ & ప్రాంతం: Sector {sector_code} ({region_name})\n'
            f'• మీ స్థానం నుండి దూరం: {distance_km:.1f} కి.మీ\n'
            f'• సలహా చెల్లుబాటు: {date_str} వరకు\n\n'
            'పి.ఎఫ్.జెడ్ సలహాలు చేపలు గుమిగూడే సముద్ర లక్షణాలను సూచిస్తాయి। '
            'బయలుదేరే ముందు ఎల్లప్పుడూ స్థానిక సముద్ర భద్రతను నిర్ధారించుకోండి।'
        )
    if lang == 'ml':
        return (
            f'{land_prefix}'
            f'ഔദ്യോഗിക ഇൻകോയിസ് (INCOIS) പി.എഫ്.ഇസഡ് (PFZ) ഉപദേശക വിവരങ്ങൾ:\n'
            f'• ലാന്റിംഗ് സെന്റർ (Landing Centre): {landing_centre}\n'
            f'• ദിശ (Direction): {direction}\n'
            f'• ബെയറിംഗ് (Bearing): {bearing_deg:.0f}°\n'
            f'• തീരത്തുനിന്നുള്ള ദൂരം: {dist_coast_str}\n'
            f'• ആഴം (മീറ്റർ): {depth_str}\n'
            f'• അക്ഷാംശം (Latitude): {lat_dms} ({lat_num:.4f}°)\n'
            f'• രേഖാംശം (Longitude): {lon_dms} ({lon_num:.4f}°)\n'
            f'• സെക്ടറും മേഖലയും: Sector {sector_code} ({region_name})\n'
            f'• നിങ്ങളുടെ സ്ഥാനത്തുനിന്നുള്ള ദൂരം: {distance_km:.1f} കി.മീ\n'
            f'• കാലാവധി: {date_str} വരെ\n\n'
            'മത്സ്യങ്ങൾ കേന്ദ്രീകരിക്കാൻ സാധ്യതയുള്ള സമുദ്ര മേഖലകളെയാണ് പി.എഫ്.ഇസഡ് സൂചിപ്പിക്കുന്നത്। '
            'യാത്ര തിരിക്കുന്നതിന് മുമ്പ് എല്ലായ്പ്പോഴും കടൽ സുരക്ഷാ മുന്നറിയിപ്പുകൾ പരിശോധിക്കുക।'
        )
    if lang == 'bn':
        return (
            f'{land_prefix}'
            f'অফিসিয়াল ইনকোইস (INCOIS) পিএফজেড (PFZ) পরামর্শের বিবরণ:\n'
            f'• অবতরণ কেন্দ্র (Landing Centre): {landing_centre}\n'
            f'• দিক (Direction): {direction}\n'
            f'• কোণ (Bearing): {bearing_deg:.0f}°\n'
            f'• উপকূল থেকে দূরত্ব: {dist_coast_str}\n'
            f'• গভীরতা (মিটার): {depth_str}\n'
            f'• অক্ষাংশ (Latitude): {lat_dms} ({lat_num:.4f}°)\n'
            f'• দ্রাঘিমাংশ (Longitude): {lon_dms} ({lon_num:.4f}°)\n'
            f'• সেক্টর ও অঞ্চল: Sector {sector_code} ({region_name})\n'
            f'• বর্তমান অবস্থান থেকে দূরত্ব: {distance_km:.1f} কিমি\n'
            f'• পরামর্শের মেয়াদ: {date_str} পর্যন্ত\n\n'
            'পিএফজেড পরামর্শ সমুদ্রের এমন অঞ্চল চিহ্নিত করে যেখানে মাছের সমাবেশ ঘটে। '
            'যাত্রার পূর্বে সর্বদা স্থানীয় সমুদ্রের নিরাপত্তা অবস্থা যাচাই করুন।'
        )
    return (
        f'{land_prefix}'
        f'Official INCOIS PFZ Advisory Details:\n'
        f'• Landing Centre: {landing_centre}\n'
        f'• Direction: {direction}\n'
        f'• Bearing (deg): {bearing_deg:.0f}°\n'
        f'• Distance (km) From - To: {dist_coast_str}\n'
        f'• Depth (mtr) From - To: {depth_str}\n'
        f'• Latitude (dms): {lat_dms} ({lat_num:.4f}°)\n'
        f'• Longitude (dms): {lon_dms} ({lon_num:.4f}°)\n'
        f'• Sector & Region: Sector {sector_code} ({region_name})\n'
        f'• Distance from position: {distance_km:.1f} km away\n'
        f'• Advisory Validity: Valid until {date_str}\n\n'
        'PFZ advisories identify oceanographic features (SST fronts and chlorophyll boundaries) '
        'favorable for pelagic fish aggregation. Always verify local sea safety conditions before departing.'
    )

def translate_marine_reading(reading_en: str, lang: str) -> str:
    if lang == 'en':
        return reading_en
    tr_map: dict[str, dict[str, str]] = {
        'Significant wave height': {
            'hi': 'सार्थक लहर ऊंचाई',
            'gu': 'મહત્વપૂર્ણ તરંગ ઊંચાઈ',
            'mr': 'सार्थक लाटांची उंची',
            'ta': 'குறிப்பிடத்தக்க அலை உயரம்',
            'te': 'ముఖ్యమైన అలల ఎత్తు',
            'ml': 'പ്രധാന തിരമാല ഉയരം',
            'bn': 'উল্লেখযোগ্য তরঙ্গের উচ্চতা',
        },
        'Wind speed': {
            'hi': 'हवा की गति',
            'gu': 'પવનની ગતિ',
            'mr': 'वाऱ्याचा वेग',
            'ta': 'காற்றின் வேகம்',
            'te': 'గాలి వేగం',
            'ml': 'കാറ്റിന്റെ വേഗത',
            'bn': 'বাতাসের গতি',
        },
        'Surface current': {
            'hi': 'सतही जलधारा',
            'gu': 'સપાટીનો પ્રવાહ',
            'mr': 'पृष्ठीय प्रवाह',
            'ta': 'மேற்பரப்பு நீரோட்டம்',
            'te': 'ఉపరితల ప్రవాహం',
            'ml': 'ഉపరిതല ഒഴുക്ക്',
            'bn': 'পৃষ্ঠীয় স্রোত',
        },
        'Sea Surface Temperature (SST)': {
            'hi': 'समुद्री सतह का तापमान (SST)',
            'gu': 'દરિયાઈ સપાટીનું તાપમાન (SST)',
            'mr': 'समुद्र पृष्ठभागाचे तापमान (SST)',
            'ta': 'கடல் மேற்பரப்பு வெப்பநிலை (SST)',
            'te': 'సముద్ర ఉపరితల ఉష్ణోగ్రత (SST)',
            'ml': 'സമുദ്രോപരിതല താപനില (SST)',
            'bn': 'সমুদ্র পৃষ্ঠের তাপমাত্রা (SST)',
        },
        'Chlorophyll-a': {
            'hi': 'क्लोरोफिल-ए',
            'gu': 'ક્લોરોફિલ-એ',
            'mr': 'क्लोरोफिल-ए',
            'ta': 'குளோரோபில்-ஏ',
            'te': 'క్లోరోఫిల్-ఎ',
            'ml': 'ക്ലോറോഫിൽ-എ',
            'bn': 'ক্লোরোফিল-এ',
        },
        'Sea level / Tide': {
            'hi': 'समुद्र स्तर / ज्वार-भाटा',
            'gu': 'દરિયાઈ સપાટી / ભરતી-ઓટ',
            'mr': 'समुद्र पातळी / भरती-ओहोटी',
            'ta': 'கடல் மட்டம் / அலை ஏற்ற இறக்கம்',
            'te': 'సముద్ర మట్టం / పోటుపాటు',
            'ml': 'സമുദ്രനിരപ്പ് / വേലിയേറ്റം',
            'bn': 'সমুদ্রের স্তর / জোয়ার-ভাটা',
        },
    }
    for prefix, translations in tr_map.items():
        if reading_en.startswith(prefix):
            localized_prefix = translations.get(lang, prefix)
            rest = reading_en[len(prefix):]
            if '(limit:' in rest:
                limit_words = {
                    'hi': '(सीमा:',
                    'gu': '(મર્યાદા:',
                    'mr': '(मर्यादा:',
                    'ta': '(வரம்பு:',
                    'te': '(పరిమితి:',
                    'ml': '(పరిధి:',
                    'bn': '(সীমা:',
                }
                rest = rest.replace('(limit:', limit_words.get(lang, '(limit:'))
            return f'{localized_prefix}{rest}'
    return reading_en

def format_marine_conditions_response(
    lang: str,
    readings: list[str],
    status_str: str,
    sources_count: int,
) -> str:
    marine_sources_count = 6 if sources_count >= 7 else sources_count
    localized_readings = [translate_marine_reading(r, lang) for r in readings]
    bullet_list = '\n'.join(f'• {r}' for r in localized_readings) if localized_readings else ''
    if not bullet_list:
        if lang == 'hi':
            return f'समुद्री डेटा संग्रह स्थिति: {status_str}। आधिकारिक नेटवर्क में {marine_sources_count} स्रोत उपलब्ध हैं।'
        if lang == 'gu':
            return f'દરિયાઈ ડેટા સંગ્રહ સ્થિતિ: {status_str}。 સત્તાવાર નેટવર્કમાં {marine_sources_count} સ્ત્રોતો ઉપલબ્ધ છે。'
        if lang == 'mr':
            return f'सागरी डेटा संकलन स्थिती: {status_str}। अधिकृत नेटवर्कमध्ये {marine_sources_count} स्त्रोत उपलब्ध आहेत।'
        if lang == 'ta':
            return f'கடல்சார் தரவு நிலை: {status_str}. அதிகாரப்பூர்வ நெட்வொர்க்கில் {marine_sources_count} ஆதாரங்கள் கிடைக்கின்றன.'
        if lang == 'te':
            return f'సముద్ర డేటా సేకరణ స్థితి: {status_str}. అధికారిక నెట్‌వర్క్‌లో {marine_sources_count} మూలాలు అందుబాటులో ఉన్నాయి.'
        if lang == 'ml':
            return f'സമുദ്ര വിവര ശേഖരണ നില: {status_str}. ഔദ്യോഗിക ശൃംഖലയിൽ {marine_sources_count} ഉറവിടങ്ങൾ ലഭ്യമാണ്.'
        if lang == 'bn':
            return f'সামুদ্রিক তথ্য সংগ্রহের অবস্থা: {status_str}। অফিসিয়াল নেটওয়ার্কে {marine_sources_count}টি উৎস উপলব্ধ রয়েছে।'
        return (
            f'Marine evidence collection is {status_str}. '
            f'{marine_sources_count} source(s) available across the official observation network.'
        )

    if lang == 'hi':
        return (
            f'वर्तमान समुद्री स्थिति:\n{bullet_list}\n\n'
            f'आधिकारिक अवलोकन नेटवर्क के {marine_sources_count} स्रोतों से डेटा पूर्ण रूप से सत्यापित है।'
        )
    if lang == 'gu':
        return (
            f'હાલની દરિયાઈ સ્થિતિ:\n{bullet_list}\n\n'
            f'સત્તાવાર નિરીક્ષણ નેટવર્કના {marine_sources_count} સ્ત્રોતોમાંથી માહિતી સંપૂર્ણપણે ઉપલબ્ધ છે.'
        )
    if lang == 'mr':
        return (
            f'सध्याची सागरी परिस्थिती:\n{bullet_list}\n\n'
            f'अधिकृत निरीक्षण नेटवर्कमधील {marine_sources_count} स्त्रोतांकडील माहिती पूर्णपणे उपलब्ध आहे.'
        )
    if lang == 'ta':
        return (
            f'தற்போதைய கடல் நிலை:\n{bullet_list}\n\n'
            f'அதிகாரப்பூர்வ கண்காணிப்பு நெட்வொர்க்கின் {marine_sources_count} மூலங்களிலிருந்து தரவு முழுமையாக சரிபார்க்கப்பட்டது.'
        )
    if lang == 'te':
        return (
            f'ప్రస్తుత సముద్ర పరిస్థితులు:\n{bullet_list}\n\n'
            f'అధికారిక పరిశీలన నెట్‌వర్క్ యొక్క {marine_sources_count} మూలాల నుండి డేటా పూర్తిగా అందుబాటులో ఉంది.'
        )
    if lang == 'ml':
        return (
            f'നിലവിലെ സമുദ്ര സാഹചര്യങ്ങൾ:\n{bullet_list}\n\n'
            f'ഔദ്യോഗിക നിരീക്ഷണ ശൃംഖലയുടെ {marine_sources_count} ഉറവിടങ്ങളിൽ നിന്നുള്ള വിവരങ്ങൾ പൂർണ്ണമായി ലഭ്യമാണ്.'
        )
    if lang == 'bn':
        return (
            f'বর্তমান সামুদ্রিক অবস্থা:\n{bullet_list}\n\n'
            f'অফিসিয়াল পর্যবেক্ষণ নেটওয়ার্কের {marine_sources_count}টি উৎস থেকে সংগৃহীত প্রমাণ সম্পূর্ণ।'
        )
    return (
        f'Current marine conditions at this location:\n{bullet_list}\n\n'
        f'Evidence status is {status_str} across {marine_sources_count} available official source(s).'
    )

def format_assessment_response(
    lang: str,
    outcome: str,
    confidence: str,
    readings: list[str],
) -> str:
    outcome_map = {
        'Within Configured Limits': {
            'hi': 'निर्धारित सीमाओं के भीतर (सुरक्षित)',
            'gu': 'રૂપરેખાંકિત મર્યાદાઓની અંદર (સલામત)',
            'mr': 'विहित मर्यादेत (सुरक्षित)',
            'ta': 'வரம்புகளுக்குள் (பாதுகாப்பானது)',
            'te': 'పరిమితుల్లో ఉంది (సురక్షితం)',
            'ml': 'പരിധിക്കുള്ളിൽ (സുരക്ഷിതം)',
            'bn': 'নির্ধারিত সীমার মধ্যে (নিরাপদ)',
        },
        'Limit Exceeded': {
            'hi': 'सीमा पार (असुरक्षित)',
            'gu': 'મર્યાદા વટાવી ગઈ (અસુરક્ષિત)',
            'mr': 'मर्यादा ओलांडली (असुरक्षित)',
            'ta': 'வரம்பு தாண்டியது (பாதுகாப்பற்றது)',
            'te': 'పరిమితి మించింది (అసురక్షితం)',
            'ml': 'పరిధి കവിഞ്ഞു (അപകടകരം)',
            'bn': 'সীমা অতিক্রম করেছে (বিপজ্জনক)',
        },
        'Caution': {
            'hi': 'सावधानी आवश्यक',
            'gu': 'સાવચેતી જરૂરી',
            'mr': 'सावधगिरी बाळगा',
            'ta': 'எச்சரிக்கை தேவை',
            'te': 'హెచ్చరిక అవసరం',
            'ml': 'ജാഗ്രത പാലിക്കുക',
            'bn': 'সতর্কতা প্রয়োজন',
        },
    }
    localized_outcome = outcome_map.get(outcome, {}).get(lang, outcome)
    localized_readings = [translate_marine_reading(r, lang) for r in readings]
    bullet_list = '\n'.join(f'• {r}' for r in localized_readings) if localized_readings else ''

    if lang == 'hi':
        readings_part = f'\n\nइस स्थान पर समुद्री स्थितियां:\n{bullet_list}' if bullet_list else ''
        return f'परिचालन मूल्यांकन परिणाम: {localized_outcome} (साक्ष्य विश्वसनीयता: {confidence})।{readings_part}'
    if lang == 'gu':
        readings_part = f'\n\nઆ સ્થાને દરિયાઈ સ્થિતિ:\n{bullet_list}' if bullet_list else ''
        return f'ઓપરેશનલ મૂલ્યાંકન પરિણામ: {localized_outcome} (વિશ્વસનીયતા: {confidence}).{readings_part}'
    if lang == 'mr':
        readings_part = f'\n\nया स्थानावरील सागरी परिस्थिती:\n{bullet_list}' if bullet_list else ''
        return f'कार्यवाही मूल्यांकन निकाल: {localized_outcome} (विश्वसनीयता: {confidence}).{readings_part}'
    if lang == 'ta':
        readings_part = f'\n\nஇந்த இடத்தில் கடல் நிலவரம்:\n{bullet_list}' if bullet_list else ''
        return f'செயல்பாட்டு மதிப்பீட்டு முடிவு: {localized_outcome} (நம்பகத்தன்மை: {confidence}).{readings_part}'
    if lang == 'te':
        readings_part = f'\n\nఈ ప్రదేశంలో సముద్ర పరిస్థితులు:\n{bullet_list}' if bullet_list else ''
        return f'కార్యాచరణ అంచనా ఫలితం: {localized_outcome} (విశ్వసనీయత: {confidence}).{readings_part}'
    if lang == 'ml':
        readings_part = f'\n\nഈ സ്ഥാനത്തെ സമുദ്ര സാഹചര്യങ്ങൾ:\n{bullet_list}' if bullet_list else ''
        return f'പ്രവർത്തന വിലയിരുത്തൽ ഫലം: {localized_outcome} (വിശ്വാസ്യത: {confidence}).{readings_part}'
    if lang == 'bn':
        readings_part = f'\n\nএই অবস্থানের সামুদ্রিক অবস্থা:\n{bullet_list}' if bullet_list else ''
        return f'পরিচালন মূল্যায়ন ফলাফল: {localized_outcome} (প্রমাণের নির্ভরযোগ্যতা: {confidence})।{readings_part}'

    readings_part = f'\n\nMarine conditions at this location:\n{bullet_list}' if bullet_list else ''
    return f'Operational assessment outcome: {outcome} (evidence confidence: {confidence}).{readings_part}'

def format_default_greeting(lang: str) -> str:
    if lang == 'hi':
        return (
            'मैं संभावित मछली पकड़ने के क्षेत्रों (PFZ), वास्तविक समय समुद्री मौसम और स्थितियों '
            '(SST, लहरें, हवा, धाराएं, क्लोरोफिल, समुद्र स्तर/ज्वार), और परिचालन सीमाओं के मूल्यांकन में आपकी सहायता कर सकता हूं।'
        )
    if lang == 'gu':
        return (
            'હું સંભવિત મત્સ્યોદ્યોગ ક્ષેત્રો (PFZ), રીઅલ-ટાઇમ દરિયાઈ હવામાન અને પરિસ્થિતિઓ '
            '(SST, મોજાં, પવન, પ્રવાહો, ક્લોરોફિલ, દરિયાઈ સપાટી/ભરતી-ઓટ), અને બોટની સુરક્ષા મર્યાદાઓની ચકાસણીમાં મદદ કરી શકું છું.'
        )
    if lang == 'mr':
        return (
            'मी संभाव्य मासेमारी क्षेत्रे (PFZ), थेट सागरी हवामान आणि परिस्थिती '
            '(SST, लाटा, वारा, प्रवाह, क्लोरोफिल, समुद्र पातळी/भरती-ओहोटी), आणि बोटीच्या सुरक्षिततेच्या मर्यादा तपासण्यात मदत करू शकतो.'
        )
    if lang == 'ta':
        return (
            'சாத்தியமான மீன்பிடி மண்டலங்கள் (PFZ), நிகழ்நேர கடல் வானிலை மற்றும் நிலைமைகள் '
            '(SST, அலைகள், காற்று, நீரோட்டங்கள், குளோரோபில், கடல் மட்டம்), மற்றும் படகு செயல்பாட்டு வரம்புகளை மதிப்பிடுவதில் நான் உதவ முடியும்.'
        )
    if lang == 'te':
        return (
            'నేను సంభావ్య చేపల వేట జోన్లు (PFZ), నిజ-సమయ సముద్ర వాతావరణం మరియు పరిస్థితులు '
            '(SST, అలలు, గాలి, ప్రవాహాలు, క్లోరోఫిల్, సముద్ర మట్టం), మరియు పడవ భద్రతా పరిమితులను అంచనా వేయడంలో సహాయపడగలను.'
        )
    if lang == 'ml':
        return (
            'സാധ്യതയുള്ള മത്സ്യബന്ധന മേഖലകൾ (PFZ), തത്സമയ സമുദ്ര കാലാവസ്ഥയും സാഹചര്യങ്ങളും '
            '(SST, തിരമാലകൾ, കാറ്റ്, ഒഴുക്ക്, ക്ലോറോഫിൽ, സമുദ്രനിരപ്പ്), ബോട്ട് സുരക്ഷാ പരിധികൾ എന്നിവ വിലയിരുത്താൻ ഞാൻ സഹായിക്കാം.'
        )
    if lang == 'bn':
        return (
            'আমি সম্ভাব্য মাছ ধরার অঞ্চল (PFZ), রিয়েল-টাইম সামুদ্রিক আবহাওয়া ও পরিস্থিতি '
            '(SST, ঢেউ, বাতাস, স্রোত, ক্লোরোফিল, সমুদ্রপৃষ্ঠ/জোয়ার-ভাটা), এবং নৌযান নিরাপত্তা সীমা মূল্যায়নে সহায়তা করতে পারি।'
        )
    return (
        'I can assist with Potential Fishing Zones (PFZ), real-time marine weather and conditions '
        '(SST, waves, wind, currents, chlorophyll, sea level), and operational limit assessments.'
    )


def format_clarification_answer(lang: str, required: tuple[Any, ...]) -> str:
    field_translations: dict[str, dict[str, str]] = {
        "latitude": {
            "hi": "अक्षांश (latitude)",
            "gu": "અક્ષાંશ (latitude)",
            "mr": "अक्षांश (latitude)",
            "ta": "அட்சரேகை (latitude)",
            "te": "అక్షాంశం (latitude)",
            "ml": "അക്ഷാംശം (latitude)",
            "bn": "অক্ষাংশ (latitude)",
        },
        "longitude": {
            "hi": "देशांतर (longitude)",
            "gu": "રેખાંશ (longitude)",
            "mr": "रेखांश (longitude)",
            "ta": "தீர்க்கரேகை (longitude)",
            "te": "రేఖాంశం (longitude)",
            "ml": "രേഖാംശം (longitude)",
            "bn": "দ্রাঘিমাংশ (longitude)",
        },
        "landing centre": {
            "hi": "उतरने का केंद्र (landing centre)",
            "gu": "ઉતરાણ કેન્દ્ર (landing centre)",
            "mr": "लँडिंग केंद्र (landing centre)",
            "ta": "இறங்கும் மையம் (landing centre)",
            "te": "లాండింగ్ కేంద్రం (landing centre)",
            "ml": "ലാൻഡിംഗ് സെന്റർ (landing centre)",
            "bn": "অবতরণ কেন্দ্র (landing centre)",
        },
    }
    raw_fields = [item.value.replace("_", " ") if hasattr(item, "value") else str(item).replace("_", " ") for item in required]
    if lang == "en":
        fields_str = ", ".join(raw_fields)
        return f"Please provide the following before ORCA continues: {fields_str}."

    localized_fields = [field_translations.get(f, {}).get(lang, f) for f in raw_fields]
    fields_str = ", ".join(localized_fields)
    if lang == "hi":
        return f"आगे बढ़ने के लिए कृपया यह जानकारी दें: {fields_str}."
    if lang == "gu":
        return f"આગળ વધવા માટે કૃપા કરીને આ માહિતી આપો: {fields_str}."
    if lang == "mr":
        return f"पुढे जाण्यासाठी कृपया ही माहिती द्या: {fields_str}."
    if lang == "ta":
        return f"தொடர பின்வரும் தகவலை வழங்கவும்: {fields_str}."
    if lang == "te":
        return f"కొనసాగడానికి దయచేసి ఈ సమాచారాన్ని అందించండి: {fields_str}."
    if lang == "ml":
        return f"തുടരുന്നതിന് ദയവായി ഈ വിവരങ്ങൾ നൽകുക: {fields_str}."
    if lang == "bn":
        return f"এগিয়ে যাওয়ার জন্য অনুগ্রহ করে এই তথ্য প্রদান করুন: {fields_str}."
    return f"Please provide the following before ORCA continues: {fields_str}."


def format_planned_answer(lang: str, intent: AssistantIntent) -> str:
    if lang == "hi":
        notices_hi = {
            AssistantIntent.OFFICIAL_ALERTS: "आधिकारिक चक्रवात और बिजली की चेतावनी सीधे उपलब्ध नहीं हैं। कृपया स्वतंत्र रूप से वर्तमान समुद्री सलाह की पुष्टि करें।",
            AssistantIntent.HABITAT_SCREENING: "क्षेत्रीय आवास स्क्रीनिंग डेटा उपलब्ध नहीं है। आप समुद्री स्थिति के माध्यम से सीधे समुद्री सतह के तापमान और क्लोरोफिल की जांच कर सकते हैं।",
            AssistantIntent.PRODUCTIVITY_ANALYSIS: "वर्तमान अवलोकन से ऐतिहासिक उत्पादकता विश्लेषण उपलब्ध नहीं है।",
            AssistantIntent.LOWER_RISK_ROUTE: "स्वचालित मार्ग नेविगेशन उपलब्ध नहीं है। अपने उद्गम और गंतव्य पर स्थितियों की जांच करने के लिए PFZ यात्रा मूल्यांकन का उपयोग करें।",
            AssistantIntent.AVOIDANCE_ZONES: "प्रतिबंधित क्षेत्र स्क्रीनिंग इस दृश्य में उपलब्ध नहीं है।",
            AssistantIntent.UNSUPPORTED: "मैं संभावित मछली पकड़ने के क्षेत्रों (PFZ), वास्तविक समय समुद्री मौसम और स्थितियों (SST, लहरें, हवा, धाराएं, क्लोरोफिल, समुद्र स्तर), और परिचालन सीमाओं के मूल्यांकन में सहायता कर सकता हूं।",
            AssistantIntent.CLARIFICATION_REQUIRED: "कृपया अपने स्थान या प्रश्न का विवरण स्पष्ट करें ताकि ORCA आपकी सहायता कर सके।",
        }
        return notices_hi.get(intent, "यह सुविधा वर्तमान में उपलब्ध नहीं है।")

    if lang == "gu":
        notices_gu = {
            AssistantIntent.OFFICIAL_ALERTS: "સત્તાવાર વાવાઝોડા અને વીજળીની ચેતવણી સીધી ઉપલબ્ધ નથી. કૃપા કરીને સત્તાવાર દરિયાઈ ચેતવણીઓની સ્વતંત્ર રીતે ખાતરી કરો.",
            AssistantIntent.HABITAT_SCREENING: "પ્રાદેશિક આવાસ સ્ક્રિનિંગ ડેટા ઉપલબ્ધ નથી. તમે દરિયાઈ સ્થિતિ દ્વારા સમુદ્ર સપાટીનું તાપમાન અને ક્લોરોફિલ ચકાસી શકો છો.",
            AssistantIntent.PRODUCTIVITY_ANALYSIS: "હાલના અવલોકનો પરથી ઐતિહાસિક ઉત્પાદકતા વિશ્લેષણ ઉપલબ્ધ નથી.",
            AssistantIntent.LOWER_RISK_ROUTE: "સ્વચાલિત રૂટ નેવિગેશન ઉપલબ્ધ નથી. મૂળ અને ગંતવ્ય સ્થાનની સ્થિતિ તપાસવા માટે PFZ મુસાફરી મૂલ્યાંકનનો ઉપયોગ કરો.",
            AssistantIntent.AVOIDANCE_ZONES: "પ્રતિબંધિત ક્ષેત્ર સ્ક્રિનિંગ આ દૃશ્યમાં ઉપલબ્ધ નથી.",
            AssistantIntent.UNSUPPORTED: "હું સંભવિત મત્સ્યોદ્યોગ ક્ષેત્રો (PFZ), રીઅલ-ટાઇમ દરિયાઈ હવામાન અને પરિસ્થિતિઓ (SST, મોજાં, પવન, પ્રવાહો, ક્લોરોફિલ, દરિયાઈ સપાટી), અને બોટ સુરક્ષા મર્યાદાઓમાં મદદ કરી શકું છું.",
            AssistantIntent.CLARIFICATION_REQUIRED: "કૃપા કરીને તમારા સ્થાન અથવા પ્રશ્નની વિગતો આપો જેથી ORCA તમને મદદ કરી શકે.",
        }
        return notices_gu.get(intent, "આ ક્ષમતા ઉપલબ્ધ નથી.")

    if lang == "mr":
        notices_mr = {
            AssistantIntent.OFFICIAL_ALERTS: "अधिकृत चक्रीवादळ आणि वीज पडण्याच्या सूचना थेट उपलब्ध नाहीत. कृपया अधिकृत सागरी सल्ल्यांची पडताळणी करा.",
            AssistantIntent.HABITAT_SCREENING: "प्रादेशिक अधिवास तपासणी डेटा उपलब्ध नाही. आपण सागरी परिस्थितीद्वारे समुद्राच्या पृष्ठभागाचे तापमान आणि क्लोरोफिल तपासू शकता.",
            AssistantIntent.PRODUCTIVITY_ANALYSIS: "सध्याच्या नोंदींवरून ऐतिहासिक उत्पादकता विश्लेषण उपलब्ध नाही.",
            AssistantIntent.LOWER_RISK_ROUTE: "स्वयंचलित मार्ग नेव्हिगेशन उपलब्ध नाही. आपल्या स्थानावरील परिस्थिती तपासण्यासाठी PFZ प्रवास मूल्यमापनाचा वापर करा.",
            AssistantIntent.AVOIDANCE_ZONES: "प्रतिबंधित क्षेत्र तपासणी उपलब्ध नाही.",
            AssistantIntent.UNSUPPORTED: "मी संभाव्य मासेमारी क्षेत्रे (PFZ), थेट सागरी हवामान आणि परिस्थिती (SST, लाटा, वारा, प्रवाह, क्लोरोफिल, समुद्र पातळी), आणि मर्यादा तपासण्यात मदत करू शकतो.",
            AssistantIntent.CLARIFICATION_REQUIRED: "कृपया आपल्या स्थानाचा किंवा प्रश्नाचा तपशील द्या.",
        }
        return notices_mr.get(intent, "ही क्षमता उपलब्ध नाही.")

    if lang == "ta":
        notices_ta = {
            AssistantIntent.OFFICIAL_ALERTS: "அதிகாரப்பூர்வ புயல் மற்றும் மின்னல் எச்சரிக்கைகள் நேரடியாக கிடைக்கவில்லை. அதிகாரப்பூர்வ கடல்சார் ஆலோசனைகளை சரிபார்க்கவும்.",
            AssistantIntent.HABITAT_SCREENING: "வாழ்விட ஆய்வு தரவு கிடைக்கவில்லை. கடல் மேற்பரப்பு வெப்பநிலை மற்றும் குளோரோபில் ஆகியவற்றை கடல் நிலைகள் மூலம் சரிபார்க்கலாம்.",
            AssistantIntent.PRODUCTIVITY_ANALYSIS: "வரலாற்று உற்பத்தித்திறன் பகுப்பாய்வு கிடைக்கவில்லை.",
            AssistantIntent.LOWER_RISK_ROUTE: "தானியங்கி வழிசெலுத்தல் கிடைக்கவில்லை. புறப்படும் மற்றும் சேருமிட நிலைமைகளை சரிபார்க்க PFZ பயண மதிப்பீட்டைப் பயன்படுத்தவும்.",
            AssistantIntent.AVOIDANCE_ZONES: "தடைசெய்யப்பட்ட பகுதி சரிபார்ப்பு கிடைக்கவில்லை.",
            AssistantIntent.UNSUPPORTED: "சாத்தியமான மீன்பிடி மண்டலங்கள் (PFZ), நிகழ்நேர கடல் வானிலை மற்றும் நிலைமைகள் (SST, அலைகள், காற்று, நீரோட்டங்கள், குளோரோபில், கடல் மட்டம்) ஆகியவற்றில் உதவ முடியும்.",
            AssistantIntent.CLARIFICATION_REQUIRED: "ORCA உதவ உங்கள் இருப்பிடம் அல்லது கேள்வியின் விவரங்களை வழங்கவும்.",
        }
        return notices_ta.get(intent, "இந்த அம்சம் கிடைக்கவில்லை.")

    if lang == "te":
        notices_te = {
            AssistantIntent.OFFICIAL_ALERTS: "అధికారిక తుఫాను హెచ్చరికలు నేరుగా అందుబాటులో లేవు. దయచేసి అధికారిక సముద్ర సలహాలను ధృవీకరించుకోండి.",
            AssistantIntent.HABITAT_SCREENING: "నివాస ప్రాంత పరిశీలన డేటా అందుబాటులో లేదు. సముద్ర ఉపరితల ఉష్ణోగ్రత మరియు క్లోరోఫిల్ సముద్ర పరిస్థితుల ద్వారా తనిఖీ చేయవచ్చు.",
            AssistantIntent.PRODUCTIVITY_ANALYSIS: "చారిత్రక ఉత్పాదకత విశ్లేషణ అందుబాటులో లేదు.",
            AssistantIntent.LOWER_RISK_ROUTE: "స్వయంచాలక రూట్ నావిగేషన్ అందుబాటులో లేదు. మీ ప్రయాణ పరిస్థితులను తనిఖీ చేయడానికి PFZ ప్రయాణ అంచనాను ఉపయోగించండి.",
            AssistantIntent.AVOIDANCE_ZONES: "పరిమిత ప్రాంతాల పరిశీలన అందుబాటులో లేదు.",
            AssistantIntent.UNSUPPORTED: "నేను సంభావ్య చేపల వేట జోన్లు (PFZ), నిజ-సమయ సముద్ర వాతావరణ పరిస్థితులు (SST, అలలు, గాలి, ప్రవాహాలు, క్లోరోఫిల్, సముద్ర మట్టం) లో సహాయపడగలను.",
            AssistantIntent.CLARIFICATION_REQUIRED: "ORCA సహాయపడటానికి దయచేసి మీ ప్రదేశం లేదా వివరాలను అందించండి.",
        }
        return notices_te.get(intent, "ఈ ఫీచర్ అందుబాటులో లేదు.")

    if lang == "ml":
        notices_ml = {
            AssistantIntent.OFFICIAL_ALERTS: "ഔദ്യോഗിക ചുഴലിക്കാറ്റ് മുന്നറിയിപ്പുകൾ നേരിട്ട് ലഭ്യമല്ല. ദയവായി ഔദ്യോഗിക മുന്നറിയിപ്പുകൾ സ്വതന്ത്രമായി പരിശോധിക്കുക.",
            AssistantIntent.HABITAT_SCREENING: "ആവാസവ്യവസ്ഥാ സ്ക്രീനിംഗ് വിവരങ്ങൾ ലഭ്യമല്ല. സമുദ്രോപരിതല താപനിലയും ക്ലോറോഫിലും പരിശോധിക്കാം.",
            AssistantIntent.PRODUCTIVITY_ANALYSIS: "ചരിത്രപരമായ ഉൽപ്പാദനക്ഷമതാ വിശകലനം ലഭ്യമല്ല.",
            AssistantIntent.LOWER_RISK_ROUTE: "ഓട്ടോമേറ്റഡ് റൂട്ട് നാവിഗേഷൻ ലഭ്യമല്ല. അവസ്ഥകൾ അറിയാൻ PFZ യാത്ര വിലയിരുത്തൽ ഉപയോഗിക്കുക.",
            AssistantIntent.AVOIDANCE_ZONES: "നിയന്ത്രിത മേഖല പരിശോധന ലഭ്യമല്ല.",
            AssistantIntent.UNSUPPORTED: "സാധ്യതയുള്ള മത്സ്യബന്ധന മേഖലകൾ (PFZ), തത്സമയ സമുദ്ര കാലാവസ്ഥാ സാഹചര്യങ്ങൾ (SST, തിരമാലകൾ, കാറ്റ്, ഒഴുക്ക്, ക്ലോറോഫിൽ) എന്നിവയിൽ ഞാൻ സഹായിക്കാം.",
            AssistantIntent.CLARIFICATION_REQUIRED: "ORCA സഹായിക്കുന്നതിന് ദയവായി നിങ്ങളുടെ സ്ഥാനം വ്യക്തമാക്കുക.",
        }
        return notices_ml.get(intent, "ഈ സേവനം ലഭ്യമല്ല.")

    if lang == "bn":
        notices_bn = {
            AssistantIntent.OFFICIAL_ALERTS: "ঘূর্ণিঝড় সতর্কতা সরাসরি উপলব্ধ নেই। অনুগ্রহ করে অফিসিয়াল পরামর্শ যাচাই করুন।",
            AssistantIntent.HABITAT_SCREENING: "বাসস্থান স্ক্রীনিং ডেটা উপলব্ধ নেই। সমুদ্রপৃষ্ঠের তাপমাত্রা এবং ক্লোরোফিল পরীক্ষা করতে পারেন।",
            AssistantIntent.PRODUCTIVITY_ANALYSIS: "ঐতিহাসিক উৎপাদনশীলতা বিশ্লেষণ উপলব্ধ নেই।",
            AssistantIntent.LOWER_RISK_ROUTE: "স্বয়ংক্রিয় রুট নেভিগেশন উপলব্ধ নেই। অবস্থান চেক করতে PFZ যাত্রা মূল্যায়ন ব্যবহার করুন।",
            AssistantIntent.AVOIDANCE_ZONES: "নিষিদ্ধ এলাকা স্ক্রীনিং উপলব্ধ নেই।",
            AssistantIntent.UNSUPPORTED: "আমি সম্ভাব্য মাছ ধরার অঞ্চল (PFZ), রিয়েল-টাইম সামুদ্রিক আবহাওয়া ও পরিস্থিতি (SST, ঢেউ, বাতাস, স্রোত, ক্লোরোফিল) মূল্যায়নে সহায়তা করতে পারি।",
            AssistantIntent.CLARIFICATION_REQUIRED: "ORCA সহায়তা করার জন্য অনুগ্রহ করে আপনার অবস্থান প্রদান করুন।",
        }
        return notices_bn.get(intent, "এই সুবিধাটি উপলব্ধ নেই।")

    notices = {
        AssistantIntent.OFFICIAL_ALERTS: "Official cyclone and lightning alerts are not available directly. Please verify current maritime advisories independently.",
        AssistantIntent.HABITAT_SCREENING: "Regional habitat screening data is not available through this query. You can check sea surface temperature and chlorophyll directly via marine conditions.",
        AssistantIntent.PRODUCTIVITY_ANALYSIS: "Historical productivity analysis is not available from current point observations.",
        AssistantIntent.LOWER_RISK_ROUTE: "Automated route navigation is not available. Use PFZ journey evaluation to check conditions at your origin and destination.",
        AssistantIntent.AVOIDANCE_ZONES: "Avoidance zones and restricted area screening are not available in this view.",
        AssistantIntent.UNSUPPORTED: "I can assist with Potential Fishing Zones (PFZ), real-time marine weather and conditions (SST, waves, wind, currents, chlorophyll, sea level), and operational limit assessments.",
        AssistantIntent.CLARIFICATION_REQUIRED: "Please specify your location or query details so ORCA can assist.",
    }
    return notices.get(intent, "This capability is not available.")

