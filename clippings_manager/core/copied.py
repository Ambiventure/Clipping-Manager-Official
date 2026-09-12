"""What a copy from WhatsApp Web IS, and what a copied caption names.

The press people send the morning's cuttings as photos on WhatsApp, each with a
line under it - "Amar ujala jalandhar", "NBT Lucknow", "दैनिक जागरण दिल्ली" - and
now and then a link to a web story instead. Collect lets somebody copy a photo
and then copy its caption without leaving WhatsApp Web, and this module is the
half that reads the caption. It says what a copy IS before anything else:

*   "caption" - a newspaper, perhaps a city, perhaps a page;
*   "link" - one web address, the story itself;
*   "caption+link" - both in the one copy;
*   "picture-address" - a blob:, data: or file: address on its own, which is
    what "Copy image address" puts on the clipboard when "Copy image" was meant;
*   "nothing" - anything else, with the reason in plain English.

IT REFUSES RATHER THAN GUESSES. The name goes onto the clipping and prints above
the picture. A clipping with no name is flagged amber and somebody types one in;
a clipping with the WRONG name looks finished and goes out wrong. So anything
that is not clearly a caption is refused: a chat line ("Good morning sir"), a
headline ("Hindustan leads the way"), half a selection ("jalandhar", "The
Ind"), two messages at once. parse_caption is deliberately not used for this.
It is built to make the best of whatever a document hands it, which is the
wrong instinct for a clipboard.

NAMES ARE MATCHED AS THEY ARE SPELT, NOT AS THE NAME INDEX SCORES THEM. The
index is built for OCR and for documents, and two of its habits print wrong
names here. It scores containment, so "Muzaffarnagar" contains most of
"Srinagar", "Rudrapur" most of "Rampur", and "The Times of India Pune" all of
The Times of India, with Pune swallowed. And it compares Devanagari with the
vowel signs taken out, so "शाम" (evening) is Shimla, "सार" (summary) is
Dainik Savera and "शामली" (Shamli, a real town) is Shimla again. So the lists
are read, never written, and compared here with every letter and vowel sign
kept: a name is the paper or the city when it is one of the list's spellings.
One typing slip is forgiven in a name of seven letters or more ("Dainek
Bhaskar", "Yamuna Nagr"), and only when every word still starts with the right
letter - which is what keeps a cut-off selection ("stan Times", "जीत" from
"अजीत") from being read as a different paper.

THE NEWSPAPER HAS TO BE AT ONE END. A caption starts with the paper ("Amar
ujala jalandhar") or, now and then, ends with it ("Jalandhar Amar Ujala", and
then only behind a listed city). A paper found in the middle of a sentence is
somebody talking about it.

WHAT FOLLOWS THE PAPER HAS TO BE A PLACE, AND ALL OF IT. A listed city prints
at 1.0. A city missing from the list - Mumbai, Panipat - is kept as typed at
0.8, and 0.8 is NOT flagged amber, so it has to be a real place: it is looked
up in PLACES below, a list of towns that have editions. Anything else after a
paper - "nahi mila", "leads way", "संवाददाता", "online", a month, a surname,
the first letters of a city ("jalan") - is refused. A town missing from PLACES
is refused too, which costs one name typed by hand, and the name typed by hand
goes onto the list, so the next copy reads.

NOTHING COPIED IS KEPT OR REPEATED. This module never logs, prints or stores the
text, and every reason it gives is a fixed sentence, so a refused copy - which
might be a password somebody copied while Collect was on - is never shown back
on screen. For the same reason a word with a dot in it ("hunter2.in") is not
taken for a link: only an address that goes somewhere is. It never grows the
name lists either: a copied word is not evidence that a city exists, and
nothing here calls add_newspaper, add_edition or save.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, replace

from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein

from .assemble import address_in, unreadable
from .profiles import NameIndex

# ------------------------------------------------------------------- limits

#: A caption is a newspaper, a city and perhaps a page: a few words on a line
#: or two. These are the outer edges of that, with room to spare. Anything
#: longer is a message, a headline or a pasted paragraph.
MAX_CHARS = 300
MAX_LINES = 4
MAX_WORDS = 7
#: The longest listed masthead is four words ("The Times of India"); one spare.
MAX_PAPER_WORDS = 5
#: A place missing from the list is kept as typed only if it is this short.
#: "Navi Mumbai" is two words; "leads the way" is three and is a headline.
VERBATIM_EDITION_WORDS = 2
#: "ji", "ok", "hi", "आज" - a word this short is chat, never a city.
MIN_VERBATIM_LETTERS = 3
#: "Dainik Bhaskar Panipat 6": a trailing number this small is the page.
#: "2, 3, 7, 32, 39, 89, 123" is a list of clipping numbers, not a caption.
BARE_PAGE_MAX = 60
#: Past this, a copy is not read at all - not even for a link. The clipboard
#: watcher already stops at 1,000 characters; this is the same edge for
#: anybody calling read() directly, and it keeps every read quick.
HARD_MAX_CHARS = 2000
#: A typing slip is forgiven only in a name at least this long. "Jalandar"
#: (8) is Jalandhar; "katran" (6, Hindi for a clipping) is not Katra, "karna"
#: is not Karnal and "Aaj Taq" is not Aaj Tak - it is refused.
NEAR_MISS_LETTERS = 7
#: And the word the slip is in must be this long: "Samachr", "Nagr" - not
#: "New" for "Now", which is another word, not a slip.
SLIP_WORD_PAPER = 5
SLIP_WORD_CITY = 4

#: A link to WhatsApp itself - a group invite, a chat link - is never a story.
WHATSAPP_HOSTS = ("whatsapp.com", "whatsapp.net", "wa.me", "wa.link")
#: Schemes that are not a web page. "javascript:evil.com" and
#: "mailto:amarujala.com" have a web address in them, but are not a story.
NOT_WEB_SCHEMES = frozenset({
    "javascript", "vbscript", "mailto", "tel", "sms", "intent", "ftp", "about",
    "chrome", "view-source", "whatsapp", "market", "content", "ws", "wss",
    "blob", "data", "file",
})

#: Words that are never a city. Checked against the words left after the
#: newspaper, so "Aaj" the paper and "The Times of India" are not affected -
#: what this catches is "Amar Ujala today" and "Amar Ujala page".
CHAT_WORDS = frozenset({
    "sir", "ji", "madam", "maam", "please", "pls", "plz", "kindly", "see",
    "check", "today", "yesterday", "good", "morning", "evening", "night",
    "dear", "thanks", "thank", "you", "photo", "pic", "pics", "image",
    "attached", "news", "hello", "hi", "namaste", "ok", "okay", "here",
    "this", "that", "is", "the", "of", "and", "page", "edition",
    "सर", "जी", "कृपया", "देखें", "आज", "नमस्ते", "सुप्रभात", "धन्यवाद", "फोटो",
    "खबर",
    # Hinglish for "I", "in", "my". "Main" is also a listed edition, which is
    # why these matter after the paper Aaj: "Aaj main" is "today I".
    "main", "mein", "maine", "mai", "mera", "meri",
})

#: Mastheads that are also an everyday word. "Aaj" and "आज" are the paper Aaj
#: and the word "today", which starts half of all chat: "Aaj nahi", "aaj
#: chutti", "आज अखबार नहीं". So the paper Aaj is read only in front of a
#: listed city - never on its own, never beside a word kept as typed, and never
#: at the end of a copy.
EVERYDAY_PAPERS = frozenset({"aaj", "आज"})
#: Mastheads that are also a first name. WhatsApp Web puts the sender's name
#: over a photo, and a selection over a photo with no caption picks up just
#: that: "Ajit / 8:38 am". So these are read only with a city after them.
NAME_PAPERS = frozenset({"ajit", "ajeet", "अजीत", "ਅਜੀਤ", "bhaskar", "भास्कर",
                         "sahara"})

# ------------------------------------------------------------------- places
#: Towns and cities that have a newspaper edition, for the words after a paper
#: that are not on the edition list. Each entry is "Name/other spelling/...";
#: the first is the name, and when THAT is on the edition list the copy is
#: read as the listed city - which is how "सुल्तानपुर" becomes Sultanpur and
#: "ਜਲੰਧਰ" Jalandhar, whose list entries have no Hindi or Punjabi spelling.
#: Otherwise the words are kept as typed (the casing taken from here) at 0.8.
#:
#: Left out on purpose, because the name is also an everyday word or a common
#: name that turns up beside a paper in chat: Anand, Sagar, Salem, Gaya
#: ("gaya"/"गया" is "went", and "Bhaskar gaya" is a man called Bhaskar
#: leaving), and the Devanagari for Mau (मऊ, too short), Surat (सूरत, "face"),
#: Zira (जीरा, "cumin") and Thane as थाने ("police station"; the city is ठाणे).
PLACES = tuple(entry.strip() for entry in """
Aligarh/अलीगढ़, Prayagraj/इलाहाबाद, Ambedkar Nagar/अंबेडकर नगर, Amethi/अमेठी,
Amroha/अमरोहा, Auraiya/औरैया, Ayodhya/अयोध्या, Azamgarh/आजमगढ़,
Baghpat/Bagpat/बागपत, Bahraich/बहराइच, Ballia/बलिया, Balrampur/बलरामपुर,
Banda/बांदा, Barabanki/बाराबंकी, Basti/बस्ती, Bhadohi/भदोही,
Budaun/Badaun/बदायूं, Bulandshahr/बुलंदशहर, Chandauli/चंदौली,
Chitrakoot/चित्रकूट, Deoria/देवरिया, Etah/एटा, Etawah/इटावा,
Farrukhabad/फर्रुखाबाद, Fatehpur/फतेहपुर, Firozabad/फिरोजाबाद,
Faizabad/फैजाबाद, Ghazipur/गाजीपुर, Gonda/गोंडा, Hamirpur/हमीरपुर,
Hardoi/हरदोई, Hathras/हाथरस, Jalaun/जालौन, Orai/उरई, Jaunpur/जौनपुर,
Jhansi/झांसी, Kannauj/कन्नौज, Kanpur Dehat/कानपुर देहात, Kasganj/कासगंज,
Kaushambi/कौशांबी, Kushinagar/कुशीनगर, Padrauna/पडरौना, Lakhimpur/लखीमपुर,
Lakhimpur Kheri/लखीमपुर खीरी, Lalitpur/ललितपुर, Maharajganj/महराजगंज,
Mahoba/महोबा, Mainpuri/मैनपुरी, Mathura/मथुरा, Mau, Mirzapur/मिर्जापुर,
Muzaffarnagar/मुजफ्फरनगर, Pilibhit/पीलीभीत, Pratapgarh/प्रतापगढ़,
Rae Bareli/Raebareli/Rae Bareilly/रायबरेली, Sambhal/संभल, Shamli/शामली,
Shravasti/श्रावस्ती, Siddharthnagar/सिद्धार्थनगर, Sitapur/सीतापुर,
Sonbhadra/सोनभद्र, Sultanpur/सुल्तानपुर, Unnao/उन्नाव,
Greater Noida/ग्रेटर नोएडा, Modinagar/मोदीनगर, Kairana/कैराना,
Baraut/बड़ौत, Khatauli/खतौली, Deoband/देवबंद, Nagina/नगीना,
Najibabad/नजीबाबाद, Chandausi/चंदौसी, Dhampur/धामपुर,

Roorkee/रुड़की, Haldwani/हल्द्वानी, Nainital/नैनीताल, Almora/अल्मोड़ा,
Pithoragarh/पिथौरागढ़, Rudrapur/रुद्रपुर, Kashipur/काशीपुर,
Rishikesh/ऋषिकेश, Kotdwar/Kotdwara/कोटद्वार, Pauri/पौड़ी, Tehri/टिहरी,
Uttarkashi/उत्तरकाशी, Chamoli/चमोली, Gopeshwar/गोपेश्वर,
Rudraprayag/रुद्रप्रयाग, Bageshwar/बागेश्वर, Champawat/चंपावत,
Mussoorie/मसूरी, Vikasnagar/विकासनगर,

Karnal/करनाल, Kurukshetra/कुरुक्षेत्र, Kaithal/कैथल, Panipat/पानीपत,
Sonipat/Sonepat/सोनीपत, Rohtak/रोहतक, Jhajjar/झज्जर, Jind/जींद,
Hisar/Hissar/हिसार, Sirsa/सिरसा, Fatehabad/फतेहाबाद, Bhiwani/भिवानी,
Charkhi Dadri/चरखी दादरी, Dadri/दादरी, Rewari/रेवाड़ी,
Mahendragarh/महेंद्रगढ़, Narnaul/नारनौल, Gurugram/Gurgaon/गुरुग्राम/गुड़गांव,
Faridabad/फरीदाबाद, Palwal/पलवल, Nuh/नूंह/नूह, Kalka/कालका,
Pinjore/पिंजौर, Jagadhri/जगाधरी, Ambala Cantt/अंबाला कैंट,
Ambala City/अंबाला सिटी,

Mohali/मोहाली/ਮੋਹਾਲੀ, SAS Nagar, Khanna/खन्ना/ਖੰਨਾ, Moga/मोगा/ਮੋਗਾ,
Faridkot/फरीदकोट/ਫਰੀਦਕੋਟ, Kapurthala/कपूरथला/ਕਪੂਰਥਲਾ,
Fazilka/फाजिल्का/ਫਾਜ਼ਿਲਕਾ, Muktsar/मुक्तसर/ਮੁਕਤਸਰ, Muktsar Sahib,
Gurdaspur/गुरदासपुर/ਗੁਰਦਾਸਪੁਰ, Hoshiarpur/होशियारपुर/ਹੁਸ਼ਿਆਰਪੁਰ,
Sirhind/सरहिंद/ਸਰਹਿੰਦ, Jalandhar/ਜਲੰਧਰ, Amritsar/ਅੰਮ੍ਰਿਤਸਰ,
Ludhiana/ਲੁਧਿਆਣਾ, Patiala/ਪਟਿਆਲਾ, Bathinda/ਬਠਿੰਡਾ, Firozpur/ਫਿਰੋਜ਼ਪੁਰ,
Pathankot/ਪਠਾਨਕੋਟ, Chandigarh/ਚੰਡੀਗੜ੍ਹ, Barnala/बरनाला/ਬਰਨਾਲਾ,
Sangrur/संगरूर/ਸੰਗਰੂਰ, Mansa/मानसा/ਮਾਨਸਾ,
Rupnagar/Ropar/रूपनगर/रोपड़/ਰੂਪਨਗਰ/ਰੋਪੜ, Nawanshahr/नवांशहर/ਨਵਾਂਸ਼ਹਿਰ,
SBS Nagar, Fatehgarh Sahib/फतेहगढ़ साहिब, Tarn Taran/तरनतारन/ਤਰਨ ਤਾਰਨ,
Batala/बटाला/ਬਟਾਲਾ, Phagwara/फगवाड़ा/ਫਗਵਾੜਾ, Rajpura/राजपुरा/ਰਾਜਪੁਰਾ,
Malerkotla/मलेरकोटला/ਮਾਲੇਰਕੋਟਲਾ, Abohar/अबोहर/ਅਬੋਹਰ, Zira, Nabha/नाभा/ਨਾਭਾ,
Kharar/खरड़/ਖਰੜ, Zirakpur/जीरकपुर, Dera Bassi/Derabassi/डेराबस्सी,
Anandpur Sahib, Jagraon/जगरांव,

Solan/सोलन, Una/ऊना, Kangra/कांगड़ा, Mandi/मंडी, Kullu/कुल्लू, Chamba/चंबा,
Nahan/नाहन, Palampur/पालमपुर, Dharamshala/Dharamsala/धर्मशाला,
Bilaspur/बिलासपुर, Kinnaur/किन्नौर,

Srinagar/श्रीनगर, Kathua/कठुआ, Udhampur/उधमपुर, Katra/कटरा,
Anantnag/अनंतनाग, Baramulla/बारामूला, Sopore/सोपोर, Kupwara/कुपवाड़ा,
Pulwama/पुलवामा, Shopian/शोपियां, Kulgam/कुलगाम, Budgam/बडगाम,
Ganderbal/गांदरबल, Bandipora/बांदीपोरा, Rajouri/राजौरी, Poonch/पुंछ,
Doda/डोडा, Kishtwar/किश्तवाड़, Ramban/रामबन, Reasi/रियासी, Samba/सांबा,
Leh/लेह, Kargil/कारगिल,

NCR/एनसीआर, Delhi NCR/दिल्ली एनसीआर, Delhi Cantt,

Patna/पटना, Bhagalpur/भागलपुर, Muzaffarpur/मुजफ्फरपुर,
Darbhanga/दरभंगा, Purnia/पूर्णिया, Ara/Arrah/आरा, Begusarai/बेगूसराय,
Katihar/कटिहार, Munger/मुंगेर, Chhapra/Chapra/छपरा, Siwan/सीवान,
Gopalganj/गोपालगंज, Motihari/मोतिहारी, Bettiah/बेतिया, Sitamarhi/सीतामढ़ी,
Madhubani/मधुबनी, Samastipur/समस्तीपुर, Hajipur/हाजीपुर, Sasaram/सासाराम,
Buxar/बक्सर, Nalanda/नालंदा, Bihar Sharif/बिहारशरीफ, Nawada/नवादा,
Jehanabad/जहानाबाद, Saharsa/सहरसा, Supaul/सुपौल, Araria/अररिया,
Kishanganj/किशनगंज,

Ranchi/रांची, Jamshedpur/जमशेदपुर, Dhanbad/धनबाद, Bokaro/बोकारो,
Hazaribagh/हजारीबाग, Deoghar/देवघर, Dumka/दुमका, Giridih/गिरिडीह,

Bhopal/भोपाल, Indore/इंदौर, Gwalior/ग्वालियर, Jabalpur/जबलपुर,
Ujjain/उज्जैन, Rewa/रीवा, Satna/सतना, Ratlam/रतलाम, Dewas/देवास,
Khandwa/खंडवा, Burhanpur/बुरहानपुर, Chhindwara/छिंदवाड़ा, Guna/गुना,
Shivpuri/शिवपुरी, Morena/मुरैना, Bhind/भिंड, Datia/दतिया, Vidisha/विदिशा,
Hoshangabad/होशंगाबाद, Narmadapuram/नर्मदापुरम, Betul/बैतूल, Katni/कटनी,
Singrauli/सिंगरौली, Shahdol/शहडोल, Chhatarpur/छतरपुर, Tikamgarh/टीकमगढ़,
Damoh/दमोह, Mandsaur/मंदसौर, Neemuch/नीमच, Khargone/खरगोन,

Jaipur/जयपुर, Jodhpur/जोधपुर, Udaipur/उदयपुर, Kota/कोटा, Ajmer/अजमेर,
Bikaner/बीकानेर, Alwar/अलवर, Bharatpur/भरतपुर, Sikar/सीकर,
Jhunjhunu/झुंझुनू, Churu/चूरू, Sri Ganganagar/Ganganagar/श्रीगंगानगर/गंगानगर,
Hanumangarh/हनुमानगढ़, Bhilwara/भीलवाड़ा, Chittorgarh/चित्तौड़गढ़,
Pali/पाली, Barmer/बाड़मेर, Jaisalmer/जैसलमेर, Nagaur/नागौर, Tonk/टोंक,
Sawai Madhopur/सवाई माधोपुर, Dholpur/धौलपुर, Karauli/करौली, Dausa/दौसा,
Banswara/बांसवाड़ा, Dungarpur/डूंगरपुर, Sirohi/सिरोही, Abu Road/आबू रोड,

Mumbai/मुंबई, Navi Mumbai/नवी मुंबई, Thane/ठाणे, Pune/पुणे, Nagpur/नागपुर,
Nashik/नासिक, Aurangabad/औरंगाबाद, Kolhapur/कोल्हापुर, Solapur/सोलापुर,
Chennai/चेन्नई, Kolkata/कोलकाता, Bengaluru/Bangalore/बेंगलुरु,
Hyderabad/हैदराबाद, Secunderabad/सिकंदराबाद, Ahmedabad/अहमदाबाद, Surat,
Vadodara/Baroda/वडोदरा, Rajkot/राजकोट, Gandhinagar/गांधीनगर,
Bhavnagar/भावनगर, Jamnagar/जामनगर, Raipur/रायपुर, Durg/दुर्ग, Bhilai/भिलाई,
Bhubaneswar/Bhubaneshwar/भुवनेश्वर, Cuttack/कटक, Guwahati/गुवाहाटी,
Siliguri/सिलीगुड़ी, Kochi/Cochin/कोच्चि, Thiruvananthapuram/Trivandrum,
Visakhapatnam/Vizag, Vijayawada, Coimbatore, Madurai, Mangaluru/Mangalore,
Mysuru/Mysore, Goa/गोवा, Panaji, Karimnagar, Warangal,

Punjab/पंजाब/ਪੰਜਾਬ, Haryana/हरियाणा, Bihar/बिहार, Rajasthan/राजस्थान,
Uttarakhand/उत्तराखंड, Jharkhand/झारखंड, Uttar Pradesh/उत्तर प्रदेश,
Madhya Pradesh/मध्य प्रदेश, Himachal Pradesh/हिमाचल प्रदेश, Kashmir/कश्मीर,
Chhattisgarh/छत्तीसगढ़
""".split(",") if entry.strip())

# ------------------------------------------------------------------ patterns
# Kept as plain strings, so a reader can see each one whole; compiled below.

DATE_NUM = r"(?<!\d)\d{1,2}[./-]\d{1,2}[./-]\d{2,4}(?!\d)"
MONTHS = (r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?"
          r"|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?"
          r"|nov(?:ember)?|dec(?:ember)?)")
DAY_MONTH = (rf"(?i)(?<!\w)\d{{1,2}}(?:st|nd|rd|th)?\s+{MONTHS}\.?"
             rf"(?:,?\s+\d{{4}})?(?!\w)")
MONTH_DAY = (rf"(?i)(?<!\w){MONTHS}\.?\s+\d{{1,2}}(?:st|nd|rd|th)?"
             rf"(?:,?\s+\d{{4}})?(?!\w)")
DATE_HI = (r"[0-9०-९]{1,2}\s*(?:जनवरी|फरवरी|फ़रवरी|मार्च|अप्रैल|मई|जून|जुलाई|अगस्त"
           r"|सितंबर|सितम्बर|अक्टूबर|अक्तूबर|नवंबर|नवम्बर|दिसंबर|दिसम्बर)"
           r"(?:\s*[0-9०-९]{4})?")
#: The word a date is often written behind: "Dated 11.09.2026", "Dt. 11/09",
#: "दिनांक 11.09.2026". Taken out with the date, or it is left as a stray word.
DATE_LABEL = r"(?:(?<![\wऀ-ॿ])(?:dated|date|dt|दिनांक|दि)\.?\s*[-:]{0,2}\s*)?"

#: What WhatsApp Web puts in front of each message when several are copied
#: together: "[10:15 am, 11/09/2026] Karan NR Degree 360: ".
PREFIX = (r"^\[\d{1,2}[:.]\d{2}(?:\s?[AaPp]\.?\s?[Mm]\.?)?,\s*"
          r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\]\s*[^:\n]{1,60}:\s*")
#: The "Forwarded" label over a forwarded bubble, on its own line or in front.
FORWARDED_LINE = r"(?i)^\[?forwarded(?: many times)?\]?$"
FORWARDED_LEAD = r"(?i)^\[forwarded(?: many times)?\]\s*"
#: The time in the corner of a bubble, which a drag-selection picks up - on a
#: line of its own, or run onto the end of the caption, with or without a
#: space ("Amar ujala jalandhar8:38 am"). Either way it ends that bubble.
TIME_ONLY = r"(?i)^(?:edited\s+)?\d{1,2}[:.]\d{2}(?:\s?[ap]\.?\s?m\.?)?$"
TIME_TAIL = (r"(?i)(?:\s+|(?<=[^\W\d_])|(?<=[ऀ-ॿ]))(?:edited\s+)?"
             r"\d{1,2}[:.]\d{2}(?:\s?[ap]\.?\s?m\.?)?$")
#: How WhatsApp Web shows the name of a sender who is not in your contacts:
#: "~ Ajit Kumar" on its own line. A name, never a caption - and "Ajit" is a
#: newspaper, so read as one it would be "Ajit, Kumar".
SENDER_LINE = r"^~\s"
#: A numbered list: "1. Amar Ujala Jalandhar", "2) NBT Lucknow".
LIST_MARK = r"^\d{1,2}[.)]\s+"
#: WhatsApp's *bold*, _italic_ and ~strike~ marks. None of them is ever part
#: of a name, wherever it stands: "*Amar Ujala*Jalandhar" is three words.
MARKUP = r"[*_~]+"
#: "P-4", "Page No. 4", "pg 12", "page no- 2", "Page :- 3", "P. No. 3", "pp 4".
#: Not a number that starts a date: "pg 12.09.2026" is not page 12.
PAGE_EN = (r"(?i)(?<!\w)(?:page|pg|pp|p)\.?\s*(?:number|num|no|#)?\.?\s*"
           r"[-.:#]{0,3}\s*([0-9०-९੦-੯]{1,3})(?!\w)(?![./-][0-9])")
#: "पेज 3", "पृष्ठ ४", "पृ. सं. 7", "पेज न. 3", "पन्ना 3", Punjabi "ਪੰਨਾ ੩".
PAGE_HI = (r"(?:पेज|पृष्ठ|पृ\.?|पन्ना|ਪੰਨਾ|ਪੇਜ)\s*"
           r"(?:नंबर|नम्बर|नं\.?|न\.|संख्या|सं\.?|ਨੰਬਰ|ਨੰ\.?)?\s*[-.:]{0,3}\s*"
           r"([0-9०-९੦-੯]{1,3})(?!\w)(?![./-][0-9])")
#: "Front page" is page 1.
FRONT_PAGE = r"(?i)(?<!\w)front[\s-]*page(?!\w)"

_DATES = tuple(re.compile(DATE_LABEL + p.removeprefix("(?i)"), re.I)
               for p in (DATE_NUM, DAY_MONTH, MONTH_DAY, DATE_HI))
_PREFIX = re.compile(PREFIX)
_FORWARDED_LINE = re.compile(FORWARDED_LINE)
_FORWARDED_LEAD = re.compile(FORWARDED_LEAD)
_TIME_ONLY = re.compile(TIME_ONLY)
_TIME_TAIL = re.compile(TIME_TAIL)
_SENDER_LINE = re.compile(SENDER_LINE)
_LIST_MARK = re.compile(LIST_MARK)
_MARKUP = re.compile(MARKUP)
_PAGES = (re.compile(PAGE_EN), re.compile(PAGE_HI))
_FRONT_PAGE = re.compile(FRONT_PAGE)
#: Words that describe the cutting or where it was seen, rather than name it:
#: "Amar Ujala E-Paper Jalandhar", "Amar Ujala online", "HT link: https://..".
#: "\w" cannot see a Devanagari vowel sign, so the edges are guarded with the
#: whole Devanagari block as well: "संस्करणों" is a different word.
_NOT_A_NAME = re.compile(
    r"(?i)(?<![\wऀ-ॿ])(?:e[-\s]?paper|edition|संस्करण|web\s*story|story\s*link"
    r"|website|web|online|digital|link|लिंक|ऑनलाइन|डिजिटल|वेब|city|सिटी)(?![\wऀ-ॿ])")
#: "N.B.T", "H.T", "T.O.I": initials with dots, which are the listed "NBT".
_INITIALS = re.compile(r"^[^\W\d_](?:\.[^\W\d_])+$")
_HOST = re.compile(r"^(?:[a-z][a-z0-9+.-]*://)?(?:[^@/\s]+@)?([^/:?#\s]+)", re.I)
_SCHEME = re.compile(r"^[^\w]*([a-z][a-z0-9+.-]*):", re.I)
#: Where a web address starts inside a token it is glued into:
#: "Jalandhar:https://..", "👉https://..", "Link:-https://..".
_ADDRESS_START = re.compile(r"(?i)https?://|www\.")
#: A picture's own address, as "Copy image address" gives it. "File:" or
#: "Data:" on their own are ordinary words in front of a caption.
_PICTURE = re.compile(r"(?i)^(?:blob:\S|data:[a-z-]+/[\w.+-]+[;,]|file:/)")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
#: What a name is compared as: letters, vowel signs and digits kept, anything
#: else a space. Unlike the name index, a Devanagari vowel sign is KEPT.
_FOLD_DROP = re.compile(r"[^\w\u0300-\u036f\u0900-\u097f\u0a00-\u0a7f]+|_+")

#: Characters that are in the text but not in what anybody reads: zero-width
#: spaces and joiners, the direction marks WhatsApp wraps round a name, the
#: byte-order mark, a soft hyphen, the Arabic letter mark, the tag characters
#: that spell out a flag emoji, variation selectors. Left in, "‎NBT Lucknow‎"
#: is not "NBT Lucknow", and the readability check counts them as mojibake.
_INVISIBLE = {
    **dict.fromkeys([*range(0x200B, 0x2010), *range(0x202A, 0x202F),
                     *range(0x2060, 0x2065), *range(0x2066, 0x206A),
                     *range(0xFE00, 0xFE10), *range(0xE0000, 0xE0080),
                     *range(0xE0100, 0xE01F0),
                     0xFEFF, 0x00AD, 0x061C, 0x180E, 0x034F]),
    0x00A0: " ", 0x202F: " ", 0x2007: " ", 0x2009: " ",
}
#: Punctuation that separates the parts of a caption and is never part of a
#: name: "Amar Ujala, Jalandhar | Page 3", "(Jalandhar)", "दिल्ली।".
_SEPARATORS = {ord(ch): " " for ch in ",|/\\;:()[]\"'“”‘’"
               "«»।॥–—&+"}
#: What a sentence, or WhatsApp, leaves stuck to the end of a link.
_LINK_TAIL = ".,;:!?'\")]}>»…।॥*_~"

# ------------------------------------------------------------------ reasons
# Fixed sentences, so a refused copy is never repeated back to the screen.
# Written to follow "Not used - ".

WHY_EMPTY = "the copy was empty"
WHY_SEVERAL = "it was several messages at once"
WHY_PICTURE_ADDRESS = "it was the address of a picture, not the picture itself"
WHY_HAS_PICTURE_ADDRESS = "it had a picture address in it"
WHY_TWO_ADDRESSES = "it had more than one web address"
WHY_WHATSAPP_LINK = "it was a WhatsApp link, not a story"
WHY_NOT_A_STORY = "it was not a link to a story"
WHY_TOO_LONG = "it is too long to be a caption"
WHY_UNREADABLE = "it could not be read as words"
WHY_TWO_PAGES = "it has two different page numbers"
WHY_NO_PAPER = "it did not start with a newspaper on the list"
WHY_TOO_MANY_WORDS = "it has too many words for a newspaper and a city"
WHY_NUMBERS = "it has numbers that are not a page"
WHY_NOT_A_CITY = "the words after the newspaper are not a city"
WHY_TWO_PAPERS = "it names two newspapers"
WHY_TWO_CAPTIONS = "it had more than one caption in it"
WHY_MISSPELT_PAPER = "the newspaper's name looks misspelt"


@dataclass(frozen=True)
class Reading:
    """What one copy was, and for a caption, what it names."""

    kind: str                   # caption | link | caption+link | picture-address | nothing
    text: str = ""              # the cleaned caption line; becomes caption_raw
    newspaper: str = ""
    edition: str = ""
    page: str = ""              # ASCII digits, whatever script it was typed in
    url: str = ""
    edition_known: bool = True  # False when the city was kept as typed
    page_from_bare_number: bool = False
    paper_known: bool = True    # False when the paper was spelt out from Hindi
    confidence: float = 0.0
    reason: str = ""            # plain English; never contains the copied text

    @property
    def display(self) -> str:
        """As the card would print it: 'Newspaper, Edition, Page N'.

        The same rule as Clip.display_caption: a page is only ever added to a
        name, never printed on its own.
        """
        parts = [p for p in (self.newspaper.strip(), self.edition.strip()) if p]
        if parts and self.page.strip():
            parts.append(f"Page {self.page.strip()}")
        return ", ".join(parts)

    @property
    def has_caption(self) -> bool:
        return self.kind in ("caption", "caption+link")

    @property
    def has_link(self) -> bool:
        return self.kind in ("link", "caption+link")


def _nothing(reason: str) -> Reading:
    return Reading(kind="nothing", reason=reason)


def _link(url: str) -> Reading:
    return Reading(kind="link", url=url)


# ----------------------------------------------------------------- cleaning


def _drop_time(line: str) -> tuple[str, bool]:
    """(the line without a bubble's time at its end, whether there was one).

    Only the last few characters are looked at. The pattern starts with a run
    of spaces, and searched over a whole line of them it is tried from every
    one - a copy of 20,000 spaces took seven seconds. A time is short.
    """
    tail = line[-40:]
    found = _TIME_TAIL.search(tail)
    if not found:
        return line, False
    return (line[:len(line) - len(tail)] + tail[:found.start()]).rstrip(), True


def _cleaned(text: str) -> tuple[list[list[str]], int]:
    """The copy's bubbles - each a list of lines - with WhatsApp's own
    furniture taken off, and how many lines carried a '[time, date] Name:'
    prefix.

    A bubble ends where its time is: on a line of its own, or on the end of
    the last line. So "Amar Ujala / 10:15 am / Jalandhar / 10:16 am" is two
    bubbles, and a caption is never put together out of two messages.
    """
    body = unicodedata.normalize("NFC", text or "")
    body = body.replace("\r\n", "\n").replace("\r", "\n").translate(_INVISIBLE)
    bubbles, lines, prefixed = [], [], 0
    for line in body.splitlines():
        line = line.strip()
        if not line or _FORWARDED_LINE.match(line) or _SENDER_LINE.match(line):
            continue
        line = _FORWARDED_LEAD.sub("", line)
        line, found = _PREFIX.subn("", line, count=1)
        prefixed += found
        line = _LIST_MARK.sub("", line.strip())
        ended = bool(_TIME_ONLY.match(line))
        if not ended:
            line, ended = _drop_time(line)
            if line:
                lines.append(line)
        if ended and lines:
            bubbles.append(lines)
            lines = []
    if lines:
        bubbles.append(lines)
    return bubbles, prefixed


def clean(text: str) -> list[str]:
    """The copy's lines, without the marks, labels and times WhatsApp adds.

    Takes off invisible characters, a "Forwarded" label, the "[10:15 am,
    11/09/2026] Name:" prefix of a multi-message copy, the "~ Name" line of a
    sender who is not in your contacts, a list number, and a bubble's time.
    Leaves the words alone: deciding what they are is read()'s job.
    """
    return [line for bubble in _cleaned(text)[0] for line in bubble]


def _host(address: str) -> str:
    """The site an address points at, without 'www.'.

    Folded the way a browser folds it before going there - full-width letters
    made plain, a backslash taken as a slash, the trailing dot of "wa.me."
    dropped - so a WhatsApp link cannot pass for a story by being spelt oddly.
    """
    plain = unicodedata.normalize("NFKC", address.strip()).replace("\\", "/")
    found = _HOST.match(plain)
    host = found.group(1).lower().rstrip(".") if found else ""
    return host[4:] if host.startswith("www.") else host


def _is_whatsapp(host: str) -> bool:
    return any(host == h or host.endswith("." + h) for h in WHATSAPP_HOSTS)


def _decoration(ch: str) -> bool:
    """An emoji, a skin tone, a variation selector: decoration, never a name."""
    return (unicodedata.category(ch) in ("So", "Sk", "Cs", "Co")
            or ch in "︎️⃣"
            or 0x1F3FB <= ord(ch) <= 0x1F3FF)


def _unmark(line: str) -> str:
    """One line with WhatsApp's formatting marks, the emoji and any stray
    control character taken out.

    Replaced by spaces rather than deleted, so "Amar Ujala🙏Jalandhar" stays
    three words and does not become "UjalaJalandhar".
    """
    line = _MARKUP.sub(" ", _CONTROL.sub(" ", line.replace("```", " ")))
    line = "".join(" " if _decoration(ch) else ch for ch in line)
    return " ".join(line.split())


# ------------------------------------------------------------ names, as spelt


#: ङ ञ ण न म with a virama, in front of a consonant: the conjunct nasal.
_NASAL_CONJUNCT = re.compile("[\u0919\u091e\u0923\u0928\u092e]\u094d(?=[\u0915-\u0939])")


def _fold(text: str) -> str:
    """A name as it is compared here: case, punctuation and spacing ignored,
    every letter and vowel sign kept.

    The nukta and the chandrabindu are the two marks people type either way
    ("गाज़ियाबाद" and "गाजियाबाद", "बदायूँ" and "बदायूं"), so those alone are
    evened out. Nothing else is: "शाम" is not "शिमला".
    """
    text = unicodedata.normalize("NFC", text or "").casefold()
    text = text.replace("\u093c", "").replace("\u0a3c", "").replace("\u0901", "\u0902")
    # A nasal before another consonant is typed two ways - "अम्बाला" with the
    # conjunct, "अंबाला" with the dot - and the office uses both for one city.
    # Folded to the dot, on both sides of every comparison. Gurmukhi's tippi
    # and bindi are the same two ways of writing the same sound.
    text = _NASAL_CONJUNCT.sub("\u0902", text)
    text = text.replace("\u0a70", "\u0a02")
    return " ".join(_FOLD_DROP.sub(" ", text).split())


def _flat(folded: str) -> str:
    return folded.replace(" ", "")


@dataclass(frozen=True)
class _Names:
    """Every spelling of every listed paper and city, folded, for one read."""

    papers: tuple   # ((name, (folded spelling, ...)), ...)
    cities: tuple


def _names(index: NameIndex) -> _Names:
    """The two lists as the index holds them, aliases and all, read once.

    NameIndex hands out the canonical names but keeps the other spellings
    ("NBT", "अमर उजाला", "नई दिल्ली") to itself, so they are read from where it
    keeps them. Read, never written - and if that ever moves, the canonical
    names alone are used, which refuses more and never guesses.
    """
    def table(held, names):
        if not isinstance(held, dict):
            held = {name: [] for name in names}
        rows = []
        for name in sorted(held):
            spelt = (_fold(s) for s in (name, *held[name]) if isinstance(s, str))
            rows.append((name, tuple(dict.fromkeys(s for s in spelt if s))))
        return tuple(rows)

    papers = table(getattr(index, "_papers", None), index.newspaper_names)
    return _Names(_with_shorthand(papers),
                  table(getattr(index, "_editions", None), index.edition_names))


#: What the office types on WhatsApp for the big papers. Kept here rather than
#: on the shared newspaper list: two letters are a fine thing to type under a
#: photo and a poor thing to go looking for inside a document's captions.
SHORTHAND = {
    "db": "Dainik Bhaskar", "dj": "Dainik Jagran", "ie": "The Indian Express",
    "pk": "Punjab Kesari", "au": "Amar Ujala", "et": "The Economic Times",
    "dt": "Dainik Tribune", "rs": "Rashtriya Sahara", "toi": "The Times of India",
    "nbt": "Navbharat Times", "ht": "Hindustan Times", "pj": "Punjabi Jagran",
}


def _with_shorthand(papers: tuple) -> tuple:
    """The paper table with the shorthand added to the papers it stands for -
    only those actually on the list, so a removed paper stays removed."""
    listed = {name: spellings for name, spellings in papers}
    for short, name in SHORTHAND.items():
        if name in listed and short not in listed[name]:
            listed[name] = listed[name] + (short,)
    return tuple((name, listed[name]) for name, _s in papers)


def _places() -> dict:
    """PLACES by folded spelling: {spelling: (name, spelling as written)}."""
    found = {}
    for entry in PLACES:
        spellings = [s.strip() for s in entry.split("/") if s.strip()]
        for spelling in spellings:
            key = _fold(spelling)
            for form in (key, _flat(key)):
                found.setdefault(form, (spellings[0], spelling))
    return found


#: Built once, from the constant above; nothing copied ever goes into it.
_PLACE_BY_SPELLING = _places()


def _one_slip(typed: str, known: str, shortest: int) -> bool:
    """Whether two folded names differ by one typing slip, and only where a
    slip is believable.

    Seven letters or more ("Jalandar", "Dainek Bhaskar"), the same number of
    words, and every word starting with the same letter. The last is what
    keeps a selection that missed the start of a name from reading as another
    one: "stan Times" is not State Times, "जीत" ("victory") is not "अजीत".

    A letter added at the END is not a slip but another word - "Hindustani",
    "Lucknowi", "Himachali" - and is not forgiven. Nor is a slip in a short
    word, where one letter makes a different word: "Times New" is not Times
    Now. A city's word may be as short as "Nagr"; a paper's must be five.
    """
    a, b = typed.split(), known.split()
    differ = [(x, y) for x, y in zip(a, b) if x != y]
    return (len(a) == len(b) and len(_flat(typed)) >= NEAR_MISS_LETTERS
            and all(x[0] == y[0] for x, y in zip(a, b))
            and all(min(len(x), len(y)) >= shortest for x, y in differ)
            and not (len(typed) == len(known) + 1 and typed.startswith(known))
            and Levenshtein.distance(typed, known) == 1)


def _find(folded: str, table: tuple, paper: bool = False) -> str:
    """The listed name spelt this way, or with one slip, or "".

    A paper's name of one word gets no slip at all: "Statesmen" and
    "Spokesmen" are English words, not The Statesman and Rozana Spokesman.
    """
    if not folded:
        return ""
    flat = _flat(folded)
    for name, spellings in table:
        if any(folded == s or flat == _flat(s) for s in spellings):
            return name
    if paper and " " not in folded:
        return ""
    shortest = SLIP_WORD_PAPER if paper else SLIP_WORD_CITY
    near = {name for name, spellings in table
            for s in spellings if _one_slip(folded, s, shortest)}
    return near.pop() if len(near) == 1 else ""


def _exact(folded: str, table: tuple) -> str:
    """The listed name spelt exactly this way, or ""."""
    flat = _flat(folded)
    for name, spellings in table:
        if folded and any(folded == s or flat == _flat(s) for s in spellings):
            return name
    return ""


# -------------------------------------------------------------------- links


def _address(token: str) -> tuple[str, str, str]:
    """(what this token is, its address, the words glued in front of it).

    What it is: "" (not an address), "story", "whatsapp", "site" - a site's
    name with nowhere to go, "amarujala.com" - or "not-web".

    address_in judges a whole line, and a token here is often a link with
    something stuck to it: "Jalandhar:https://..", "👉https://..", "Link:-
    https://..", "*https://..*". So the token is cut where the address starts,
    and what came before it stays with the caption - "Jalandhar" is the city,
    not part of the link.

    A site's name on its own is not taken as the story. It goes nowhere, it is
    how a caption mentions the paper ("Amar Ujala, amarujala.com, Page 3"),
    and a password that happens to end in ".in" looks exactly like one.
    """
    whole = token.strip()
    start = _ADDRESS_START.search(whole)
    before, body = (whole[:start.start()], whole[start.start():]) if start else ("", whole)
    found = address_in(body.strip("*_~"))
    while found and (found[-1] in _LINK_TAIL or _decoration(found[-1])):
        found = found[:-1]
    if not found:
        return "", "", ""
    scheme = _SCHEME.match(whole)
    if scheme and scheme.group(1).lower() in NOT_WEB_SCHEMES:
        return "not-web", found, ""
    parts = re.match(r"(?i)^[a-z][a-z0-9+.-]*://([^/?#]*)", found)
    if parts and "@" in parts.group(1):
        return "not-web", found, ""         # "https://user:password@site/.."
    if _is_whatsapp(_host(found)):
        return "whatsapp", found, before
    if not parts and not found.lower().startswith("www."):
        path = found.split("/", 1)[1] if "/" in found else ""
        if not path.strip("/"):
            return "site", found, before
    return "story", found, before


def _story(url: str) -> str:
    """What makes two addresses the same story: the site without "www.",
    "m." or "amp.", the path without its "/amp" part, and the query."""
    plain = unicodedata.normalize("NFKC", url).replace("\\", "/")
    found = re.match(r"(?i)^(?:[a-z][a-z0-9+.-]*://)?(?:[^@/\s]+@)?"
                     r"([^/?#\s]*)([^?#]*)(\?[^#]*)?", plain)
    host = re.sub(r"^(?:www|m|amp)\.", "", found.group(1).lower().rstrip("."))
    path = re.sub(r"(?i)/amp(?=/|$)", "", found.group(2)).rstrip("/")
    return host + path + (found.group(3) or "")


# ----------------------------------------------------------- the caption test


def _strip_dates(text: str) -> str:
    """Take out '11.09.2026', '11 Sept', 'Sept 11', '11 सितंबर', 'Dated
    11.09.2026'.

    A date is not part of the name, and left in it reads as a stray number -
    'Hindustan Times Delhi Sept 11' would be refused over the 11.
    """
    for pattern in _DATES:
        text = pattern.sub(" ", text)
    return text


def _lift_page(text: str) -> tuple[str, str, str]:
    """(page, text without it, reason if refused).

    The page may be written anywhere in the caption and in either script:
    "Dainik Bhaskar page no- 2 Firozpur", "हिंदुस्तान लखनऊ पेज 3". Two DIFFERENT
    page numbers are two captions, or a guess waiting to happen. There is no
    page 0.

    This runs BEFORE the dates come out. The other way round, "Page 3 Sept 11"
    loses "3 Sept" as a date and is read as page 11.
    """
    pages = set()
    for pattern in _PAGES:
        for match in pattern.finditer(text):
            pages.add(str(int(match.group(1))))     # int() reads ४ and ੩ too
    if _FRONT_PAGE.search(text):
        pages.add("1")
    if len(pages) > 1:
        return "", text, WHY_TWO_PAGES
    for pattern in (*_PAGES, _FRONT_PAGE):
        text = pattern.sub(" ", text)
    page = pages.pop() if pages else ""
    if page == "0":
        return "", text, WHY_NUMBERS
    return page, text, ""


def _letter(ch: str) -> bool:
    """A letter or a vowel sign. A Devanagari matra is category M, not L."""
    return unicodedata.category(ch)[0] in ("L", "M")


def _words(text: str) -> list[str]:
    """The caption cut into words, its separators taken out.

    A hyphen goes when it stands at the edge of a word - " - ", "Delhi-" - or
    joins two words, "Amar-Ujala". One between a letter and a digit stays, so
    "Delhi-4" is not quietly read as a page. Initials written with dots,
    "N.B.T.", are the listed "NBT".
    """
    text = text.translate(_SEPARATORS)
    chars = list(text)
    for i, ch in enumerate(chars):
        if ch != "-":
            continue
        before = text[i - 1] if i else " "
        after = text[i + 1] if i + 1 < len(text) else " "
        if before.isspace() or after.isspace() or (_letter(before) and _letter(after)):
            chars[i] = " "
    words = [w.strip(".") for w in "".join(chars).split()]
    return [w.replace(".", "") if _INITIALS.match(w) else w for w in words if w]


def _mentions(words: list[str], names: _Names) -> set:
    """Every listed paper spelt out, exactly, anywhere in these words."""
    found = set()
    for i in range(len(words)):
        for k in range(1, min(MAX_PAPER_WORDS, len(words) - i) + 1):
            name = _exact(_fold(" ".join(words[i:i + k])), names.papers)
            if name:
                found.add(name)
    return found


def _listed_city(words: list[str], names: _Names) -> str:
    """The listed city these words are - every one of them - or "".

    Spelt as the list spells it; or a spelling PLACES knows for a listed city
    ("सुल्तानपुर" for Sultanpur); or one typing slip away from a listed city,
    as long as the words are not a real town of their own. "Dhampur" and
    "Udhampur" are both real, and so are "Shamli" and Shimla.
    """
    folded = _fold(" ".join(words))
    if not folded:
        return ""
    listed = _exact(folded, names.cities)
    if listed:
        return listed
    place = _PLACE_BY_SPELLING.get(folded) or _PLACE_BY_SPELLING.get(_flat(folded))
    if place:
        return _exact(_fold(place[0]), names.cities)
    return _find(folded, names.cities)


def _edition(words: list[str], names: _Names) -> tuple[str, bool, str]:
    """(edition, known, reason if refused) for the words after the paper.

    A listed city is known, and printed as the list spells it. Anything else
    is kept as typed only when it is a real town (PLACES), short, and not
    chat - because 0.8 is not flagged, and "Amar Ujala nahi mila" would
    otherwise print as the Nahi Mila edition.
    """
    if not words:
        return "", True, ""
    listed = _listed_city(words, names)
    if listed:
        return listed, True, ""
    folded = _fold(" ".join(words))
    place = _PLACE_BY_SPELLING.get(folded) or _PLACE_BY_SPELLING.get(_flat(folded))
    if (place is None or len(words) > VERBATIM_EDITION_WORDS
            or any(len(w) < MIN_VERBATIM_LETTERS for w in words)
            or not all(_letter(ch) for w in words for ch in w)
            or any(w.casefold() in CHAT_WORDS for w in words)):
        # "Amar Ujala NBT" is two captions run together, not a paper in a
        # city called NBT - worth saying so, rather than "not a city".
        return "", False, WHY_TWO_PAPERS if _mentions(words, names) else WHY_NOT_A_CITY
    typed = " ".join(words)
    # Typed in English letters, the casing is taken from PLACES, so "NBT
    # MUMBAI" prints Mumbai and "HT NCR" keeps NCR. Typed in Hindi or Punjabi,
    # it prints as the town's English name, the way a listed city typed in
    # Hindi already does (दिल्ली prints Delhi): "Navbharat Times, मुंबई" beside
    # English mastheads reads as a mistake on the page.
    if typed.isascii():
        return place[1], False, ""
    return (place[0] if place[0].isascii() else typed), False, ""


def _another_paper(words: list[str], k: int, paper: str, names: _Names,
                   index: NameIndex) -> bool:
    """Whether the paper and the words after it look like a DIFFERENT listed
    masthead, misspelt - only to give a better reason for a refusal.

    "Hindustan Tiems" starts with Hindustan, and "Tiems" is not a city; the
    most useful thing to say is that the name looks misspelt.
    """
    for j in range(1, len(words) - k + 1):
        phrase = _fold(" ".join(words[:k + j]))
        for name, spellings in names.papers:
            if name != paper and any(fuzz.ratio(phrase, s) >= index.accept_score
                                     for s in spellings):
                return True
    return False


def _paper_at_end(words: list[str], names: _Names) -> tuple[str, str] | None:
    """(paper, city) for the city-first order, "Jalandhar Amar Ujala", or None.

    Only a listed city may stand in front of the paper; anything else in
    front is a sentence. Of the lengths that leave a listed city in front, an
    exact spelling beats one with a slip, and then the longer wins. The paper
    Aaj is never read here: "Main aaj" is "I, today".
    """
    n = len(words)
    end = None
    for k in range(min(MAX_PAPER_WORDS, n - 1), 0, -1):
        span = _fold(" ".join(words[n - k:]))
        paper = _find(span, names.papers, paper=True)
        if not paper or span in EVERYDAY_PAPERS:
            continue
        city = _listed_city(words[:n - k], names)
        key = (bool(_exact(span, names.papers)), k)
        if city and (end is None or key > end[0]):
            end = (key, paper, city)
    return (end[1], end[2]) if end else None


def _caption_test(candidate: str, names: _Names, index: NameIndex) -> Reading:
    """Whether one string is a caption: a Reading of kind caption, or nothing."""
    text = " ".join(candidate.split())
    page, body, why = _lift_page(text)
    if why:
        return _nothing(why)
    words = _words(_NOT_A_NAME.sub(" ", _strip_dates(body)))

    bare = False
    if (not page and len(words) >= 3 and words[-1].isdecimal()
            and 1 <= int(words[-1]) <= BARE_PAGE_MAX):
        page, words, bare = str(int(words[-1])), words[:-1], True

    if not words:
        return _nothing(WHY_NO_PAPER)
    if len(words) > MAX_WORDS:
        return _nothing(WHY_TOO_MANY_WORDS)
    # What refuses "Hindustan123", and "Amar Ujala Delhi-4".
    if any(ch.isdigit() for w in words for ch in w):
        return _nothing(WHY_NUMBERS)

    n = len(words)
    # The paper at the start. Every length that is a listed paper is weighed
    # by what it leaves behind, then by whether it is spelt exactly, then by
    # length:
    #
    # *   Leaving a listed city or nothing beats leaving a town kept as typed,
    #     which beats leaving words that are no place at all. "Hindustan Times
    #     Delhi" is Hindustan Times in Delhi, not Hindustan in "Times Delhi";
    #     "Ajit Samachr Jalandhar" is Ajit Samachar with a slip, in Jalandhar,
    #     not Ajit in "Samachr Jalandhar".
    # *   Then an exact spelling over one with a slip, and then the longer, so
    #     "News Times Ludhiana", a listed paper, is not cut to "News Times".
    best = None
    for k in range(min(MAX_PAPER_WORDS, n), 0, -1):
        span = _fold(" ".join(words[:k]))
        paper = _find(span, names.papers, paper=True)
        if not paper:
            continue
        edition, known, why = _edition(words[k:], names)
        if span in EVERYDAY_PAPERS and (
                why or not known or not edition
                or any(w.casefold() in CHAT_WORDS for w in words[k:])):
            continue
        if span in NAME_PAPERS and not edition:
            continue
        key = (0 if why else 2 if known else 1, bool(_exact(span, names.papers)), k)
        if best is None or key > best[0]:
            best = (key, paper, edition, known, why)
    if best is not None:
        (_settled, _spelt, k), paper, edition, known, why = best
        if why:
            if _another_paper(words, k, paper, names, index):
                return _nothing(WHY_MISSPELT_PAPER)
            return _nothing(why)
        # A town kept as typed after the paper, when the same words read from
        # the other end are a listed city and a listed paper: two papers fit,
        # so neither is put on the clipping.
        if not known and _paper_at_end(words, names) is not None:
            return _nothing(WHY_TWO_PAPERS)
    else:
        found = _paper_at_end(words, names)
        if found is None:
            spelt = _unlisted_paper(words, names)
            if spelt is None:
                return _nothing(WHY_NO_PAPER)
            (paper, edition), known = spelt, True
            return Reading(
                kind="caption", text=text, newspaper=paper, edition=edition,
                page=page, edition_known=True, page_from_bare_number=bare,
                paper_known=False, confidence=UNLISTED_PAPER_CONFIDENCE,
            )
        (paper, edition), known = found, True

    return Reading(
        kind="caption",
        text=text,
        newspaper=paper,
        edition=edition,
        page=page,
        edition_known=known,
        page_from_bare_number=bare,
        confidence=1.0 if known else 0.8,
    )


#: Below the card's amber line (0.75), on purpose: a masthead spelt out from
#: Hindi by rule is worth checking, and the flag is what asks for the check.
UNLISTED_PAPER_CONFIDENCE = 0.7


def _indic(word: str) -> bool:
    """Whether every letter is Devanagari or Gurmukhi."""
    return bool(word) and all(
        "\u0900" <= ch <= "\u097f" or "\u0a00" <= ch <= "\u0a7f" for ch in word)


def _unlisted_paper(words: list[str], names: _Names) -> tuple[str, str] | None:
    """(paper spelt out in English, listed city) for a Hindi or Punjabi
    caption whose paper is not on the list, or None.

    "वीर अर्जुन दिल्ली" is a real Delhi daily the list does not know. Refusing it
    left the clipping unnamed; naming it Veer Arjun by rule, in Delhi, and
    flagging it amber gets the clipping most of the way and asks for a look.
    Held to a narrow shape so chat cannot pass: every word in Hindi or Punjabi,
    one to three words in front, none of them chat, and a LISTED city after
    them. A town merely kept as typed does not count - that would be two
    guesses on one line.
    """
    if len(words) < 2 or not all(_indic(w) for w in words):
        return None
    for k in range(1, min(3, len(words) - 1) + 1):
        head, tail = words[:k], words[k:]
        # Chat starts with a chat word - "सुप्रभात दिल्ली", "कृपया देखें दिल्ली".
        # A masthead may hold one further in: Prabhat KHABAR is a paper.
        if head[0].casefold() in CHAT_WORDS or all(w.casefold() in CHAT_WORDS
                                                   for w in head):
            return None
        if any(len(w) < 2 for w in head):
            continue
        city = _listed_city(tail, names)
        if city:
            return " ".join(romanise(w) for w in head), city
    return None


# ------------------------------------------------------------ spelling out
#
# Hindi and Punjabi mastheads the list does not know, written in English by
# rule - "Veer Arjun", "Jansatta". Not a transliteration standard, which nobody
# in the office reads: the everyday spelling, with the silent "a" dropped where
# Hindi drops it (जागरण is Jagran, not Jagarana). It is a guess by rule, and
# every name it makes is flagged for a check.

_DEVA_VOWELS = {
    "अ": "a", "आ": "a", "इ": "i", "ई": "i", "उ": "u", "ऊ": "u", "ऋ": "ri",
    "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au", "ऑ": "o", "ऍ": "e",
}
_DEVA_SIGNS = {
    "ा": "a", "ि": "i", "ी": "i", "ु": "u", "ू": "u", "ृ": "ri", "े": "e",
    "ै": "ai", "ो": "o", "ौ": "au", "ॉ": "o", "ॅ": "e",
}
_DEVA_CONS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n", "च": "ch", "छ": "chh",
    "ज": "j", "झ": "jh", "ञ": "n", "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh",
    "ण": "n", "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n", "प": "p",
    "फ": "ph", "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r", "ल": "l",
    "ळ": "l", "व": "v", "श": "sh", "ष": "sh", "स": "s", "ह": "h",
}
_DEVA_NUKTA = {"क": "q", "ख": "kh", "ग": "g", "ज": "z", "ड": "r", "ढ": "rh",
               "फ": "f", "य": "y"}
_GURU_VOWELS = {
    "ਅ": "a", "ਆ": "a", "ਇ": "i", "ਈ": "i", "ਉ": "u", "ਊ": "u", "ਏ": "e",
    "ਐ": "ai", "ਓ": "o", "ਔ": "au",
}
_GURU_SIGNS = {"ਾ": "a", "ਿ": "i", "ੀ": "i", "ੁ": "u", "ੂ": "u", "ੇ": "e",
               "ੈ": "ai", "ੋ": "o", "ੌ": "au"}
_GURU_CONS = {
    "ਕ": "k", "ਖ": "kh", "ਗ": "g", "ਘ": "gh", "ਙ": "n", "ਚ": "ch", "ਛ": "chh",
    "ਜ": "j", "ਝ": "jh", "ਞ": "n", "ਟ": "t", "ਠ": "th", "ਡ": "d", "ਢ": "dh",
    "ਣ": "n", "ਤ": "t", "ਥ": "th", "ਦ": "d", "ਧ": "dh", "ਨ": "n", "ਪ": "p",
    "ਫ": "ph", "ਬ": "b", "ਭ": "bh", "ਮ": "m", "ਯ": "y", "ਰ": "r", "ਲ": "l",
    "ਵ": "v", "ੜ": "r", "ਸ": "s", "ਹ": "h",
}
_GURU_NUKTA = {"ਸ": "sh", "ਜ": "z", "ਫ": "f", "ਖ": "kh", "ਗ": "g", "ਲ": "l"}


def _syllables(word: str) -> list:
    """A word cut into [consonant, vowel, inherent] pieces, either script."""
    word = unicodedata.normalize("NFD", word)
    out: list = []
    i, double = 0, False
    while i < len(word):
        ch = word[i]
        nukta = i + 1 < len(word) and word[i + 1] in ("\u093c", "\u0a3c")
        if ch in _DEVA_CONS or ch in _GURU_CONS:
            table, nuktas = ((_DEVA_CONS, _DEVA_NUKTA) if ch in _DEVA_CONS
                             else (_GURU_CONS, _GURU_NUKTA))
            latin = nuktas.get(ch, table[ch]) if nukta else table[ch]
            if double:
                latin, double = latin[0] + latin, False
            i += 2 if nukta else 1
            nxt = word[i] if i < len(word) else ""
            if nxt in _DEVA_SIGNS or nxt in _GURU_SIGNS:
                out.append([latin, (_DEVA_SIGNS.get(nxt) or _GURU_SIGNS[nxt]), False])
                i += 1
            elif nxt in ("\u094d", "\u0a4d"):
                out.append([latin, "", False])       # a joined consonant
                i += 1
            else:
                out.append([latin, "a", True])
            continue
        if ch in _DEVA_VOWELS or ch in _GURU_VOWELS:
            out.append(["", _DEVA_VOWELS.get(ch) or _GURU_VOWELS[ch], False])
        elif ch in ("\u0902", "\u0901", "\u0a02", "\u0a70") and out:
            out[-1][1] += "n"                        # the nasal dot
        elif ch == "\u0903" and out:
            out[-1][1] += "h"
        elif ch == "\u0a71":
            double = True                            # Gurmukhi's addak
        i += 1
    return out


#: English words that mastheads carry, written in Hindi or Punjabi letters.
#: Spelt out by sound they come back as "Taims" and "Ekspres"; these are what
#: the paper itself prints on its front page.
LOANWORDS = {
    "टाइम्स": "Times", "टाईम्स": "Times", "ਟਾਈਮਜ਼": "Times", "ਟਾਈਮਸ": "Times",
    "एक्सप्रेस": "Express", "ਐਕਸਪ੍ਰੈਸ": "Express", "न्यूज़": "News", "न्यूज": "News",
    "ਨਿਊਜ਼": "News", "ट्रिब्यून": "Tribune", "ਟ੍ਰਿਬਿਊਨ": "Tribune",
    "हेराल्ड": "Herald", "मेल": "Mail", "पोस्ट": "Post", "टुडे": "Today",
    "स्टेट्समैन": "Statesman", "पायनियर": "Pioneer", "मिरर": "Mirror",
    "स्पोक्समैन": "Spokesman", "ਸਪੋਕਸਮੈਨ": "Spokesman", "स्टार": "Star",
    "क्रॉनिकल": "Chronicle", "गार्जियन": "Guardian", "टेलीग्राफ": "Telegraph",
    "नेशनल": "National", "इंडिया": "India", "ਇੰਡੀਆ": "India", "इंडियन": "Indian",
    "हिंदुस्तान": "Hindustan", "हिन्दुस्तान": "Hindustan", "पंजाब": "Punjab",
    "ਪੰਜਾਬ": "Punjab", "पंजाबी": "Punjabi", "ਪੰਜਾਬੀ": "Punjabi", "केसरी": "Kesari",
    "ਕੇਸਰੀ": "Kesari", "जागरण": "Jagran", "ਜਾਗਰਣ": "Jagran", "वीर": "Veer",
}


def romanise(word: str) -> str:
    """One Hindi or Punjabi word in everyday English spelling."""
    known = LOANWORDS.get(unicodedata.normalize("NFC", word))
    if known:
        return known
    parts = _syllables(word)
    if not parts:
        return word
    if parts[-1][2]:
        # No "a" on the end - except after an "i", where English keeps it:
        # Rashtriya, Bharatiya. The nasal dot on that syllable stays either way.
        before = next((q[1] for q in reversed(parts[:-1]) if q[1]), "")
        if not (parts[-1][0] == "y" and before.startswith("i")):
            parts[-1][1] = parts[-1][1][1:]
    # The silent "a" in the middle: dropped after a sounded vowel when the next
    # sounded consonant has a vowel of its own - जागरण to Jagran, जनसत्ता to
    # Jansatta - from the right, so two in a row never both go.
    for at in range(len(parts) - 2, 0, -1):
        cons, vowel, inherent = parts[at]
        if not inherent or not vowel:
            continue
        before = next((p[1] for p in reversed(parts[:at]) if p[1]), "")
        after = next((p for p in parts[at + 1:] if p[0]), None)
        if before and after is not None and after[1]:
            parts[at][1] = vowel[1:]                 # keeps a nasal: ਜਲੰਧਰ
    spelt = "".join(cons + vowel for cons, vowel, _inherent in parts)
    return spelt[:1].upper() + spelt[1:]


def _caption_in(lines: list[str], names: _Names, index: NameIndex) -> Reading:
    """The caption in one bubble's lines, or nothing.

    The lines together first - a caption can wrap - and each on its own,
    which lets a sender's name above the caption fail while the caption
    passes. Two lines that each pass and disagree are two captions ("Hindustan"
    over "Times Now" is not Hindustan Times, whatever the two read as
    together). And a line AFTER the caption that names another paper is a
    reply correcting it - "Amar ujala Jammu / wrong name, correct is NBT
    Lucknow" - so the quoted caption is not used.
    """
    joined = _caption_test(" ".join(lines), names, index)
    if len(lines) == 1:
        return joined
    singles = [_caption_test(line, names, index) for line in lines]
    passed = [i for i, r in enumerate(singles) if r.has_caption]
    if len({(singles[i].newspaper, singles[i].edition, singles[i].page)
            for i in passed}) > 1:
        return _nothing(WHY_TWO_CAPTIONS)
    if joined.has_caption:
        return joined
    if not passed:
        return _nothing(joined.reason)
    found = singles[passed[0]]
    for line in lines[passed[-1] + 1:]:
        if _mentions(_words(line), names) - {found.newspaper}:
            return _nothing(WHY_TWO_PAPERS)
    return found


def _read_bubble(lines: list[str], names: _Names, index: NameIndex) -> Reading:
    """What one bubble's worth of the copy is."""
    stories, seen, whatsapp, site, rest = [], set(), False, False, []
    for line in lines:
        kept = []
        for token in line.split():
            kind, found, before = _address(token)
            if not kind:
                kept.append(token)
                continue
            if before:
                kept.append(before)
            if kind == "not-web":
                return _nothing(WHY_NOT_A_STORY)
            if kind == "whatsapp":
                whatsapp = True
            elif kind == "site":
                site = True
            elif _story(found) not in seen:
                # One address is the story. Two are a guess about which - but
                # the same story twice, with and without "www." or "/amp", is
                # still one.
                seen.add(_story(found))
                stories.append(found)
                if len(stories) > 1:
                    return _nothing(WHY_TWO_ADDRESSES)
        if kept:
            rest.append(" ".join(kept))
    if whatsapp and not stories:
        return _nothing(WHY_WHATSAPP_LINK)
    url = stories[0] if stories else ""
    if not rest:
        return _link(url) if url else _nothing(WHY_NOT_A_STORY if site else WHY_EMPTY)

    # Past these limits it is not a caption, but a link that came with a
    # headline or a paragraph is still a link: the words are simply not used.
    if len("\n".join(rest)) > MAX_CHARS or len(rest) > MAX_LINES:
        return _link(url) if url else _nothing(WHY_TOO_LONG)
    if unreadable(" ".join(rest)):
        return _link(url) if url else _nothing(WHY_UNREADABLE)
    rest = [line for line in (_unmark(line) for line in rest) if line]
    if not rest:
        return _link(url) if url else _nothing(WHY_EMPTY)

    found = _caption_in(rest, names, index)
    if not found.has_caption:
        return _link(url) if url else found
    return replace(found, kind="caption+link", url=url) if url else found


# --------------------------------------------------------------------- read


def read(text: str, index: NameIndex) -> Reading:
    """What this copy is, and for a caption what it names. Never raises on
    odd text, never changes the index, and gives the same answer every time."""
    text = text if isinstance(text, str) else ""
    if len(text) > HARD_MAX_CHARS:
        return _nothing(WHY_TOO_LONG)
    bubbles, prefixed = _cleaned(text)
    if prefixed >= 2:
        return _nothing(WHY_SEVERAL)
    tokens = [token for bubble in bubbles for line in bubble for token in line.split()]
    if not tokens:
        return _nothing(WHY_EMPTY)

    # A picture's own address. On its own it is the "Copy image address"
    # mis-click, which the caller has to hear about, because the photo it was
    # meant to be never arrived. Inside other text it is nothing to act on.
    for token in tokens:
        if _PICTURE.match(token.strip("()[]<>\"'")):
            if len(tokens) == 1:
                return Reading(kind="picture-address", reason=WHY_PICTURE_ADDRESS)
            return _nothing(WHY_HAS_PICTURE_ADDRESS)

    # Each bubble on its own. A selection that ran over two messages is only
    # used when they say the same thing: taking one of two would put the
    # previous photo's name, or its link, on this one.
    names = _names(index)
    said = [r for r in (_read_bubble(b, names, index) for b in bubbles)
            if r.reason != WHY_EMPTY]
    if not said:
        return _nothing(WHY_EMPTY)
    if all(replace(r, text="") == replace(said[0], text="") for r in said):
        return said[0]
    if len({(r.newspaper, r.edition, r.page) for r in said if r.has_caption}) > 1:
        return _nothing(WHY_TWO_CAPTIONS)
    if len({_story(r.url) for r in said if r.url}) > 1:
        return _nothing(WHY_TWO_ADDRESSES)
    return _nothing(WHY_SEVERAL)


def caption_values(reading: Reading) -> dict:
    """The seven clipping fields a copied caption sets, ready for one undo step.

    Empty for anything that is not a caption, so passing it on can never
    blank a name. The label is deliberately not among them: a headline the
    user typed keeps printing, with the page added after it.
    """
    if not reading.has_caption:
        return {}
    return {
        "caption_raw": reading.text,
        "newspaper": reading.newspaper,
        "edition": reading.edition,
        "page": reading.page,
        "name_source": "copied",
        "name_confidence": reading.confidence,
        "no_title": False,
    }


# ------------------------------------------------------------ into English
#
# A caption pasted or typed into a card by hand stays as it was typed - Hindi
# in the headline box, printing in Hindi over an English report. "Put in
# English" is the button for that: the card's Hindi is read the way a copied
# caption is read, and what it names is written into the fields in English.
# Nothing is guessed that the reader would not guess: a listed paper is spelt
# as the list spells it, one it does not know is spelt out by rule and
# flagged, and a Hindi HEADLINE - a sentence, not a paper and a city - is left
# exactly alone, because a headline in Hindi is what the paper printed.


@dataclass(frozen=True)
class English:
    """What putting one clipping's Hindi into English would do."""

    changes: dict               # field -> (old, new); empty when left alone
    said: str                   # one line for the summary
    flagged: bool = False       # a name spelt out by rule: worth a look
    nothing: bool = False       # no Hindi on the card at all - not a line


def has_indic(text: str) -> bool:
    """Whether any of this is written in Hindi or Punjabi letters."""
    return any("\u0900" <= ch <= "\u097f" or "\u0a00" <= ch <= "\u0a7f"
               for ch in (text or ""))


def needs_english(clip) -> bool:
    """Whether the card has Hindi or Punjabi in a field the report prints."""
    return any(has_indic(getattr(clip, name, ""))
               for name in ("label", "newspaper", "edition"))


def _paper_in_english(typed: str, names: _Names) -> tuple[str, bool]:
    """(name in English, spelt out by rule?) for a Hindi newspaper field."""
    words = _words(typed)
    listed = _find(_fold(" ".join(words)), names.papers, paper=True)
    if listed:
        return listed, False
    return " ".join(romanise(w) for w in words), True


def _city_in_english(typed: str, names: _Names) -> tuple[str, bool]:
    words = _words(typed)
    listed = _listed_city(words, names)
    if listed:
        return listed, False
    folded = _fold(" ".join(words))
    place = _PLACE_BY_SPELLING.get(folded) or _PLACE_BY_SPELLING.get(_flat(folded))
    if place and place[0].isascii():
        return place[0], False
    return " ".join(romanise(w) for w in words), True


#: A headline box holding this many Hindi words or fewer, none of them chat,
#: is taken for a newspaper's name typed where the caption goes - "अर्थ प्रकाश
#: पंजाब" - and not for a headline. A real headline is longer than this.
SHORT_NAME_WORDS = 3


def _short_name(words: list[str], names: _Names) -> tuple[str, str]:
    """(paper, city) for a short all-Hindi label the reader did not take -
    a paper the list has never heard of, before a place or alone.

    Returns ("", "") for anything longer than SHORT_NAME_WORDS, mixed with
    English, or holding a chat word.
    """
    if not words or len(words) > SHORT_NAME_WORDS:
        return "", ""
    if not all(has_indic(w) for w in words):
        return "", ""
    if any(w.casefold() in CHAT_WORDS for w in words):
        return "", ""
    for k in (2, 1):
        if len(words) > k:
            tail = _fold(" ".join(words[-k:]))
            place = _PLACE_BY_SPELLING.get(tail) or _PLACE_BY_SPELLING.get(_flat(tail))
            if place:
                city = _listed_city(words[-k:], names) or place[0]
                return " ".join(romanise(w) for w in words[:-k]), city
    return " ".join(romanise(w) for w in words), ""


def english_for(clip, index: NameIndex) -> English:
    """What "Put in English" would do to this clipping. Changes nothing."""
    label = (clip.label or "").strip()
    paper = (clip.newspaper or "").strip()
    city = (clip.edition or "").strip()
    if not (has_indic(label) or has_indic(paper) or has_indic(city)):
        return English({}, "nothing in Hindi", nothing=True)

    names = _names(index)
    changes: dict = {}
    notes: list = []
    flagged = False

    if has_indic(label):
        found = read(label, index)
        if found.has_caption:
            # The headline box held a caption: it moves into the fields, in
            # English, and the box is emptied so the caption prints.
            changes["label"] = (clip.label, "")
            changes["no_title"] = (clip.no_title, False)
            changes["caption_raw"] = (clip.caption_raw, label)
            changes["newspaper"] = (clip.newspaper, found.newspaper)
            paper = found.newspaper
            # A caption with no city in it leaves the card's own city alone -
            # respelt below if it is in Hindi, kept if it is not.
            if found.edition:
                changes["edition"] = (clip.edition, found.edition)
                city = found.edition
            if found.page:
                changes["page"] = (getattr(clip, "page", ""), found.page)
            flagged = flagged or not found.paper_known or not found.edition_known
            notes.append(f"headline \u201c{label}\u201d \u2192 {found.display}")
        else:
            short_paper, short_city = _short_name(_words(label), names)
            if short_paper:
                # A paper the list does not know, typed where the caption
                # goes: moved into the fields, spelt out by rule, flagged.
                changes["label"] = (clip.label, "")
                changes["no_title"] = (clip.no_title, False)
                changes["caption_raw"] = (clip.caption_raw, label)
                changes["newspaper"] = (clip.newspaper, short_paper)
                paper = short_paper
                if short_city:
                    changes["edition"] = (clip.edition, short_city)
                    city = short_city
                flagged = True
                notes.append(f"headline \u201c{label}\u201d \u2192 "
                             + ", ".join(p for p in (short_paper, short_city) if p))
            else:
                notes.append(f"headline \u201c{label}\u201d left as it is - "
                             f"{len(_words(label))} words do not read as a "
                             f"newspaper and a city")

    if has_indic(paper):
        spelt, by_rule = _paper_in_english(paper, names)
        changes["newspaper"] = (clip.newspaper, spelt)
        flagged = flagged or by_rule
        notes.append(f"\u201c{paper}\u201d \u2192 {spelt}")
    if has_indic(city):
        spelt, by_rule = _city_in_english(city, names)
        changes["edition"] = (clip.edition, spelt)
        flagged = flagged or by_rule
        notes.append(f"\u201c{city}\u201d \u2192 {spelt}")

    if any(field in changes for field in ("newspaper", "edition")):
        changes["name_source"] = (clip.name_source, "copied")
        changes["name_confidence"] = (clip.name_confidence,
                                      UNLISTED_PAPER_CONFIDENCE if flagged else 1.0)
    said = "; ".join(notes) + (" (spelt out by rule - check it)" if flagged else "")
    return English(changes, said, flagged=flagged)
