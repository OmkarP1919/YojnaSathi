/**
 * Centralized UI strings for YojnaSathi frontend.
 * Supports English (en - default), Hindi (hi), and Marathi (mr).
 * Strictly avoids definitive legal qualification claims.
 */
export const STRINGS = {
  en: {
    // Header
    appTitle: "YojnaSathi",
    appTagline: "Find government schemes made simple",
    newSearch: "New Search",
    homeNav: "Home",
    languageSelect: "Language",

    // Home Page & Category Grid
    heroBadge: "Civic Scheme Discovery",
    heroTitle: "Find government schemes made for you",
    heroSubtitle: "Answer a few simple questions and discover schemes that may be relevant to you.",
    categoryHeading: "What kind of help are you looking for?",
    categorySubtitle: "Select a category to start finding schemes tailored to your needs.",

    // Categories
    catFarmersTitle: "Farmers",
    catFarmersDesc: "Farming, crop insurance, and financial support.",
    catWomenTitle: "Women",
    catWomenDesc: "Support, financial assistance, and welfare schemes.",
    catEducationTitle: "Education",
    catEducationDesc: "Scholarships, student support, and education schemes.",
    catHealthcareTitle: "Healthcare",
    catHealthcareDesc: "Health insurance and medical support.",
    catHousingTitle: "Housing",
    catHousingDesc: "Housing assistance and related schemes.",
    catEmploymentTitle: "Employment",
    catEmploymentDesc: "Jobs, skills, and employment support.",
    catBusinessTitle: "Small Business",
    catBusinessDesc: "Loans and support for businesses and street vendors.",

    // Questionnaire
    questionnaireTitlePrefix: "Finding schemes for",
    questionnaireSubtitle: "Let's find schemes that may be useful for you. This will only take a minute.",
    stepIndicator: "Step {current} of {total}",
    backButton: "← Back",
    continueButton: "Continue →",
    submitButton: "Find Relevant Schemes 🎯",
    findingSchemesLoading: "Finding schemes that may be relevant to you...",
    selectOptionPrompt: "Please select an option to continue.",

    // Questionnaire Common Questions
    ageQuestion: "How old are you?",
    agePlaceholder: "Enter your age in years (e.g. 35)",
    ageError: "Please enter a valid age between 10 and 120 years.",
    stateQuestion: "Where do you live?",
    statePlaceholder: "-- Select your State / UT --",
    stateError: "Please select your state from the list.",
    incomeQuestion: "What is your approximate yearly family income?",
    incomeBelow25: "Below ₹2.5 Lakh",
    income25to6: "₹2.5 Lakh – ₹6 Lakh",
    incomeAbove6: "Above ₹6 Lakh",
    incomeDontKnow: "I don't know / Prefer not to say",

    // Social Category Questions
    socialCategoryQuestion: "Which social category do you belong to?",
    socialCatGeneral: "General / Open Category",
    socialCatSC: "Scheduled Caste (SC)",
    socialCatST: "Scheduled Tribe (ST)",
    socialCatOBC: "Other Backward Class (OBC)",
    socialCatEBC: "Economically Backward Class (EBC)",
    socialCatDNT: "De-notified, Nomadic or Semi-Nomadic Tribe (DNT / NT)",
    socialCatDontKnow: "I don't know / Prefer not to say",

    // Rural / Urban Area Questions
    areaQuestion: "Do you reside in a rural village or an urban city area?",
    areaRural: "Rural village area",
    areaUrban: "Urban city / town area",
    areaDontKnow: "I don't know / Not sure",

    // Farmers Questions
    farmerLandQuestion: "Do you or your family own cultivable agricultural land?",
    farmerLandYes: "Yes, we own agricultural land",
    farmerLandNo: "No, tenant/sharecropper or landless",
    farmerLandDontKnow: "I don't know / Not sure",
    farmerNeedQuestion: "What kind of help do you need?",
    farmerNeedCropInsurance: "Crop insurance (protection against crop damage)",
    farmerNeedDirectSupport: "Direct financial support (income support for farmers)",
    farmerNeedEquipment: "Farming equipment & agricultural inputs",
    farmerNeedLoan: "Agricultural credit or loan",

    // Women Questions
    womenStatusQuestion: "What is your current situation?",
    womenStatusMarried: "Married woman",
    womenStatusUnmarried: "Unmarried woman",
    womenStatusPregnant: "Pregnant or lactating mother",
    womenStatusWidow: "Widow, deserted, or single woman",
    womenStatusGeneral: "Prefer not to specify",
    womenNeedQuestion: "What kind of support are you looking for?",
    womenNeedFinance: "Monthly financial assistance for women",
    womenNeedGas: "Free LPG / cooking gas connection",
    womenNeedMaternity: "Maternity & pregnancy financial assistance",
    womenNeedTraining: "Skill training & self-employment support",

    // Education Questions
    eduStatusQuestion: "Are you currently a student or pursuing education?",
    eduStatusYes: "Yes, currently studying in school/college",
    eduStatusNo: "No, seeking educational opportunities/skill training",
    eduNeedQuestion: "What type of educational support do you need?",
    eduNeedScholarship: "School or pre/post-matric scholarship",
    eduNeedHigherEdu: "Higher education financial support & coaching",
    eduNeedSkill: "Skill development & vocational certification",

    // Healthcare Questions
    healthNeedQuestion: "What kind of healthcare assistance do you need?",
    healthNeedHospital: "Hospital treatment & surgery cover",
    healthNeedInsurance: "Free health insurance card (up to ₹5 Lakh)",
    healthNeedSenior: "Senior citizen health coverage (Age 70+)",
    healthNeedCritical: "Critical illness or hospitalization support",

    // Housing Questions
    housingPuccaQuestion: "Do you or your family currently own a pucca (permanent) house?",
    housingPuccaNo: "No, living in kutcha house, temporary shelter, or rented",
    housingPuccaYes: "Yes, we own a permanent pucca house",
    housingPuccaDontKnow: "I don't know / Not sure",
    housingAreaQuestion: "Where are you planning to construct or buy a house?",
    housingAreaRural: "Rural village area (PMAY-Gramin)",
    housingAreaUrban: "Urban / city / municipal area (PMAY-Urban)",

    // Employment Questions
    empStatusQuestion: "What is your current employment status?",
    empStatusUnemployed: "Job seeker / Unemployed",
    empStatusWage: "Daily wage worker / Rural laborer",
    empStatusYouth: "Youth seeking skill training & certification",
    empStatusUnorganized: "Unorganized sector worker",
    empNeedQuestion: "What kind of employment support do you need?",
    empNeedWage: "100 days guaranteed rural wage employment (MGNREGA)",
    empNeedSkill: "Free skill development & industry training (PMKVY)",
    empNeedPension: "Old-age pension & retirement security (APY)",
    empNeedAccident: "Low-cost accidental insurance cover (PMSBY)",

    // Small Business Questions
    bizStatusQuestion: "What type of business activity do you do?",
    bizStatusVendor: "Street vendor / Cart vendor / Hawker",
    bizStatusSmallBiz: "Small business / Retail shop owner",
    bizStatusSelf: "Micro-entrepreneur / Self-employed",
    bizStatusAspiring: "Planning to start a new micro-enterprise",
    bizNeedQuestion: "What kind of financial assistance do you need?",
    bizNeedWorkingCap: "Collateral-free working capital loan (PM SVANidhi)",
    bizNeedMudra: "Business loan for micro-enterprise (MUDRA)",
    bizNeedBank: "Zero-balance bank account with overdraft & insurance (PMJDY)",

    // Results Page
    resultsTitle: "Schemes that may be relevant to you",
    resultsCountPrefix: "We found",
    resultsCountSuffix: "schemes based on the information you provided.",
    noticeLabel: "Notice:",
    disclaimerText: "These schemes are potentially relevant based on the information provided. Final eligibility is determined by the relevant government authority.",
    noResultsTitle: "We couldn't find schemes that closely match the information provided",
    noResultsText: "Based on the information provided, we could not find directly matching schemes in this category. Try adjusting your answers or starting a new search.",
    changeAnswers: "Change Answers",
    startNewSearch: "Start New Search",

    // Scheme Card
    matchRelevance: "Match relevance:",
    whyRelevant: "Why this may be relevant",
    infoNeeded: "Information you may need",
    viewDetails: "View Scheme Details",
    hideDetails: "Hide Details",

    // Dynamic Reason Codes
    reason_ALL_INDIA_AVAILABLE: "Applicable across India, including {state}",
    reason_STATE_SPECIFIC_MATCH: "Specifically available for residents of {state}",
    reason_TARGET_GROUP_FARMER: "Relevant for farmers and rural citizens",
    reason_TARGET_GROUP_STUDENT: "Relevant for students and youth",
    reason_TARGET_GROUP_WOMEN: "Provides targeted support for women",
    reason_TARGET_GROUP_BUSINESS: "Relevant for small businesses, vendors, and entrepreneurs",
    reason_TARGET_GROUP_WORKER: "Relevant for unorganized and unskilled workers",
    reason_NEED_MATCH: "Matches your selected interest in this scheme category",
    reason_AGE_CRITERIA_MATCH: "Your age ({age} years) matches the scheme criteria",
    reason_INCOME_CRITERIA_MATCH: "Your family income is within the scheme's threshold",
    reason_LAND_OWNERSHIP_MATCH: "Matches your agricultural landholding status",
    reason_SOCIAL_CATEGORY_MATCH: "Matches your social category ({category})",
    reason_AREA_MATCH: "Specifically designed for {area} areas",
    reason_HOUSING_NEED_MATCH: "Addresses households without a permanent pucca house",

    // Scheme Detail Modal
    modalTitle: "Scheme Details",
    departmentLabel: "Department / Ministry:",
    aboutLabel: "About this scheme",
    benefitsLabel: "Key Benefits",
    documentsLabel: "Information you may need",
    applyButton: "Apply / Learn more ↗",
    sourceButton: "Official source portal ↗",
    closeModal: "Close",
    loadingDetails: "Loading verified scheme information...",

    // Errors
    errorTitle: "We couldn't find your schemes right now.",
    errorGeneric: "An unexpected issue occurred while finding relevant schemes. Please try again.",
    errorNetwork: "Unable to connect to the YojnaSathi server. Please check your internet connection or verify the backend is running.",
    tryAgain: "Try Again",
    startOver: "Start Over",
  },

  hi: {
    // Header
    appTitle: "योजनासाथी",
    appTagline: "सरकारी योजनाएं खोजना हुआ आसान",
    newSearch: "नई खोज",
    homeNav: "मुख्य पृष्ठ",
    languageSelect: "भाषा",

    // Home Page & Category Grid
    heroBadge: "नागरिक योजना खोज मंच",
    heroTitle: "अपने लिए उपयुक्त सरकारी योजनाएं खोजें",
    heroSubtitle: "कुछ आसान सवालों के जवाब दें और अपने लिए प्रासंगिक सरकारी योजनाएं जानें।",
    categoryHeading: "आप किस प्रकार की सहायता खोज रहे हैं?",
    categorySubtitle: "अपनी आवश्यकता के अनुसार उपयुक्त श्रेणी चुनें।",

    // Categories
    catFarmersTitle: "किसान",
    catFarmersDesc: "खेती, फसल बीमा और वित्तीय सहायता योजनाएं।",
    catWomenTitle: "महिलाएं",
    catWomenDesc: "सहायता, वित्तीय लाभ और महिला कल्याण योजनाएं।",
    catEducationTitle: "शिक्षा एवं छात्र",
    catEducationDesc: "छात्रवृत्ति, विद्यार्थी सहायता और उच्च शिक्षा योजनाएं।",
    catHealthcareTitle: "स्वास्थ्य सेवा",
    catHealthcareDesc: "स्वास्थ्य बीमा और निःशुल्क चिकित्सा उपचार सहायता।",
    catHousingTitle: "आवास योजना",
    catHousingDesc: "पक्का मकान निर्माण और आवास सहायता योजनाएं।",
    catEmploymentTitle: "रोजगार व कौशल",
    catEmploymentDesc: "रोजगार गारंटी, कौशल विकास और सामाजिक सुरक्षा।",
    catBusinessTitle: "लघु व्यवसाय",
    catBusinessDesc: "रेहड़ी-पटरी विक्रेता, मुद्रा लोन और व्यापार सहायता।",

    // Questionnaire
    questionnaireTitlePrefix: "के लिए योजनाएं खोज रहे हैं",
    questionnaireSubtitle: "आइए आपके लिए उपयुक्त योजनाएं खोजते हैं। इसमें केवल एक मिनट लगेगा।",
    stepIndicator: "चरण {current} / {total}",
    backButton: "← पीछे जाएं",
    continueButton: "आगे बढ़ें →",
    submitButton: "प्रासंगिक योजनाएं देखें 🎯",
    findingSchemesLoading: "आपके लिए प्रासंगिक योजनाएं खोजी जा रही हैं...",
    selectOptionPrompt: "कृपया आगे बढ़ने के लिए एक विकल्प चुनें।",

    // Questionnaire Common Questions
    ageQuestion: "आपकी उम्र कितनी है?",
    agePlaceholder: "अपनी उम्र दर्ज करें (उदा. 35)",
    ageError: "कृपया 10 से 120 वर्ष के बीच मान्य आयु दर्ज करें।",
    stateQuestion: "आप कहाँ रहते हैं?",
    statePlaceholder: "-- अपना राज्य / केंद्र शासित प्रदेश चुनें --",
    stateError: "कृपया सूची से अपना राज्य चुनें।",
    incomeQuestion: "आपके परिवार की अनुमानित वार्षिक आय कितनी है?",
    incomeBelow25: "₹2.5 लाख से कम",
    income25to6: "₹2.5 लाख से ₹6 लाख",
    incomeAbove6: "₹6 लाख से अधिक",
    incomeDontKnow: "पता नहीं / बताना नहीं चाहते",

    // Social Category Questions
    socialCategoryQuestion: "आप किस सामाजिक वर्ग (श्रेणी) से संबंधित हैं?",
    socialCatGeneral: "सामान्य वर्ग (General)",
    socialCatSC: "अनुसूचित जाति (SC)",
    socialCatST: "अनुसूचित जनजाति (ST)",
    socialCatOBC: "अन्य पिछड़ा वर्ग (OBC)",
    socialCatEBC: "आर्थिक रूप से पिछड़ा वर्ग (EBC)",
    socialCatDNT: "विमुक्त, घुमंतू या अर्ध-घुमंतू जनजाति (DNT / NT)",
    socialCatDontKnow: "पता नहीं / बताना नहीं चाहते",

    // Rural / Urban Area Questions
    areaQuestion: "आप ग्रामीण गाँव में रहते हैं या शहरी क्षेत्र में?",
    areaRural: "ग्रामीण क्षेत्र (गाँव)",
    areaUrban: "शहरी क्षेत्र (शहर / कस्बा)",
    areaDontKnow: "पता नहीं / निश्चित नहीं",

    // Farmers Questions
    farmerLandQuestion: "क्या आपके या आपके परिवार के नाम कृषि योग्य भूमि है?",
    farmerLandYes: "हाँ, हमारे पास कृषि भूमि है",
    farmerLandNo: "नहीं, बटाईदार / पट्टेदार या भूमिहीन हैं",
    farmerLandDontKnow: "पता नहीं / निश्चित नहीं",
    farmerNeedQuestion: "आपको किस प्रकार की सहायता चाहिए?",
    farmerNeedCropInsurance: "फसल बीमा (फसल नुकसान से सुरक्षा)",
    farmerNeedDirectSupport: "प्रत्यक्ष वित्तीय सहायता (किसान सम्मान निधि)",
    farmerNeedEquipment: "कृषि उपकरण और खाद-बीज सहायता",
    farmerNeedLoan: "कृषि ऋण या किसान क्रेडिट कार्ड",

    // Women Questions
    womenStatusQuestion: "आपकी वर्तमान स्थिति क्या है?",
    womenStatusMarried: "विवाहित महिला",
    womenStatusUnmarried: "अविवाहित युवती / महिला",
    womenStatusPregnant: "गर्भवती या स्तनपान कराने वाली माता",
    womenStatusWidow: "विधवा, परित्यक्ता या एकल महिला",
    womenStatusGeneral: "बताना नहीं चाहते",
    womenNeedQuestion: "आप किस प्रकार की सहायता खोज रही हैं?",
    womenNeedFinance: "महिलाओं के लिए मासिक आर्थिक सहायता (लाड़की बहिन)",
    womenNeedGas: "निःशुल्क एलपीजी गैस सिलेंडर कनेक्शन (उज्ज्वला)",
    womenNeedMaternity: "मातृत्व एवं गर्भावस्था आर्थिक सहायता",
    womenNeedTraining: "कौशल प्रशिक्षण एवं स्वरोजगार सहायता",

    // Education Questions
    eduStatusQuestion: "क्या आप वर्तमान में छात्र हैं या पढ़ाई कर रहे हैं?",
    eduStatusYes: "हाँ, स्कूल या कॉलेज में पढ़ाई कर रहे हैं",
    eduStatusNo: "नहीं, शिक्षा या कौशल प्रशिक्षण के अवसर खोज रहे हैं",
    eduNeedQuestion: "आपको किस प्रकार की शैक्षणिक सहायता चाहिए?",
    eduNeedScholarship: "स्कूल या प्री/पोस्ट-मैट्रिक छात्रवृत्ति",
    eduNeedHigherEdu: "उच्च शिक्षा सहायता एवं प्रतियोगी परीक्षा कोचिंग",
    eduNeedSkill: "कौशल विकास एवं व्यावसायिक प्रमाणन",

    // Healthcare Questions
    healthNeedQuestion: "आपको किस प्रकार की स्वास्थ्य सहायता चाहिए?",
    healthNeedHospital: "अस्पताल में भर्ती, उपचार एवं ऑपरेशन सहायता",
    healthNeedInsurance: "निःशुल्क स्वास्थ्य बीमा कार्ड (₹5 लाख तक)",
    healthNeedSenior: "वरिष्ठ नागरिक स्वास्थ्य सुरक्षा (70 वर्ष और अधिक)",
    healthNeedCritical: "गंभीर बीमारी या चिकित्सा उपचार सहायता",

    // Housing Questions
    housingPuccaQuestion: "क्या आपके या आपके परिवार के पास पक्का मकान है?",
    housingPuccaNo: "नहीं, कच्चे मकान, झोपड़ी या किराए पर रहते हैं",
    housingPuccaYes: "हाँ, हमारे पास पक्का मकान है",
    housingPuccaDontKnow: "पता नहीं / निश्चित नहीं",
    housingAreaQuestion: "आप मकान कहाँ बनाने या खरीदने की योजना बना रहे हैं?",
    housingAreaRural: "ग्रामीण क्षेत्र / गाँव में (पीएम आवास ग्रामीण)",
    housingAreaUrban: "शहरी क्षेत्र / नगर पालिका क्षेत्र में (पीएम आवास शहरी)",

    // Employment Questions
    empStatusQuestion: "आपकी वर्तमान रोजगार स्थिति क्या है?",
    empStatusUnemployed: "बेरोजगार / काम की तलाश में",
    empStatusWage: "दैनिक वेतनभोगी मजदूर / ग्रामीण श्रमिक",
    empStatusYouth: "युवा जो कौशल प्रशिक्षण पाना चाहते हैं",
    empStatusUnorganized: "असंगठित क्षेत्र के कामगार",
    empNeedQuestion: "आपको किस प्रकार की रोजगार सहायता चाहिए?",
    empNeedWage: "100 दिनों का गारंटीशुदा ग्रामीण रोजगार (मनरेगा)",
    empNeedSkill: "निःशुल्क कौशल विकास व उद्योग प्रशिक्षण (पीएमकेवीवाई)",
    empNeedPension: "वृद्धावस्था पेंशन व सामाजिक सुरक्षा (अटल पेंशन)",
    empNeedAccident: "कम खर्च में दुर्घटना बीमा सुरक्षा (सुरक्षा बीमा)",

    // Small Business Questions
    bizStatusQuestion: "आप किस प्रकार का व्यवसाय या कार्य करते हैं?",
    bizStatusVendor: "रेहड़ी-पटरी विक्रेता / फेरीवाले / ठेला चालक",
    bizStatusSmallBiz: "छोटा व्यवसाय / खुदरा दुकान संचालक",
    bizStatusSelf: "सूक्ष्म उद्यमी / स्वरोजगारी",
    bizStatusAspiring: "नया छोटा व्यवसाय शुरू करने की योजना",
    bizNeedQuestion: "आपको किस प्रकार की वित्तीय सहायता चाहिए?",
    bizNeedWorkingCap: "बिना गारंटी कार्यशील पूंजी ऋण (पीएम स्वनिधि ₹50,000 तक)",
    bizNeedMudra: "सूक्ष्म उद्यम हेतु व्यवसाय ऋण (मुद्रा लोन ₹10 लाख तक)",
    bizNeedBank: "जीरो-बैलेंस बैंक खाता, ओवरड्राफ्ट व बीमा (जन धन)",

    // Results Page
    resultsTitle: "आपके लिए प्रासंगिक हो सकती हैं ऐसी योजनाएँ",
    resultsCountPrefix: "आपकी दी गई जानकारी के आधार पर हमें",
    resultsCountSuffix: "योजनाएँ मिली हैं।",
    noticeLabel: "सूचना:",
    disclaimerText: "ये योजनाएँ प्रदान की गई जानकारी के आधार पर संभावित रूप से प्रासंगिक हैं। अंतिम पात्रता संबंधित सरकारी प्राधिकरण द्वारा निर्धारित की जाती है।",
    noResultsTitle: "दी गई जानकारी से मेल खाती योजनाएँ नहीं मिलीं",
    noResultsText: "आपकी दी गई जानकारी के आधार पर इस श्रेणी में सीधे मेल खाती योजनाएँ नहीं मिलीं। कृपया उत्तर बदलकर पुनः प्रयास करें।",
    changeAnswers: "उत्तर बदलें",
    startNewSearch: "नई खोज शुरू करें",

    // Scheme Card
    matchRelevance: "प्रासंगिकता स्कोर:",
    whyRelevant: "यह योजना आपके लिए क्यों प्रासंगिक हो सकती है",
    infoNeeded: "आवश्यक जानकारी व दस्तावेज",
    viewDetails: "योजना विवरण देखें",
    hideDetails: "विवरण छिपाएं",

    // Dynamic Reason Codes
    reason_ALL_INDIA_AVAILABLE: "पूरे भारत में उपलब्ध, जिसमें {state} भी शामिल है",
    reason_STATE_SPECIFIC_MATCH: "विशेष रूप से {state} के निवासियों के लिए उपलब्ध",
    reason_TARGET_GROUP_FARMER: "किसानों और ग्रामीण नागरिकों के लिए प्रासंगिक",
    reason_TARGET_GROUP_STUDENT: "विद्यार्थियों और युवाओं के लिए प्रासंगिक",
    reason_TARGET_GROUP_WOMEN: "महिलाओं के लिए लक्षित सहायता प्रदान करता है",
    reason_TARGET_GROUP_BUSINESS: "लघु व्यवसायों, फेरीवालों और उद्यमियों के लिए प्रासंगिक",
    reason_TARGET_GROUP_WORKER: "असंगठित और अकुशल श्रमिकों के लिए प्रासंगिक",
    reason_NEED_MATCH: "आपकी चुनी हुई आवश्यकता से मेल खाता है",
    reason_AGE_CRITERIA_MATCH: "आपकी आयु ({age} वर्ष) योजना के मानदंडों के अनुकूल है",
    reason_INCOME_CRITERIA_MATCH: "आपकी पारिवारिक आय योजना की सीमा के भीतर है",
    reason_LAND_OWNERSHIP_MATCH: "आपके कृषि भूमि स्वामित्व की स्थिति से मेल खाता है",
    reason_SOCIAL_CATEGORY_MATCH: "आपके सामाजिक वर्ग ({category}) के अनुकूल",
    reason_AREA_MATCH: "विशेष रूप से {area} क्षेत्रों के लिए निर्मित",
    reason_HOUSING_NEED_MATCH: "पक्के मकान से वंचित परिवारों के लिए उपयुक्त",

    // Scheme Detail Modal
    modalTitle: "योजना का संपूर्ण विवरण",
    departmentLabel: "विभाग / मंत्रालय:",
    aboutLabel: "योजना के बारे में",
    benefitsLabel: "मुख्य लाभ",
    documentsLabel: "आवश्यक जानकारी व दस्तावेज",
    applyButton: "आवेदन करें / अधिक जानें ↗",
    sourceButton: "आधिकारिक पोर्टल ↗",
    closeModal: "बंद करें",
    loadingDetails: "सत्यापित योजना जानकारी लोड हो रही है...",

    // Errors
    errorTitle: "अभी आपकी योजनाएँ नहीं मिल सकीं।",
    errorGeneric: "योजनाएं खोजते समय एक अप्रत्याशित समस्या आई। कृपया पुनः प्रयास करें।",
    errorNetwork: "सर्वर से संपर्क नहीं हो सका। कृपया इंटरनेट कनेक्शन या बैकएंड जांचें।",
    tryAgain: "पुनः प्रयास करें",
    startOver: "शुरू से करें",
  },

  mr: {
    // Header
    appTitle: "योजनासाथी",
    appTagline: "सरकारी योजना शोधणे आता झाले सोपे",
    newSearch: "नवीन शोध",
    homeNav: "मुख्य पृष्ठ",
    languageSelect: "भाषा",

    // Home Page & Category Grid
    heroBadge: "नागरिक योजना शोध मंच",
    heroTitle: "तुमच्यासाठी योग्य सरकारी योजना शोधा",
    heroSubtitle: "काही सोप्या प्रश्नांची उत्तरे द्या आणि तुमच्यासाठी उपयुक्त योजना जाणून घ्या.",
    categoryHeading: "तुम्हाला कोणत्या प्रकारची मदत हवी आहे?",
    categorySubtitle: "तुमच्या गरजेनुसार योग्य प्रवर्ग निवडा.",

    // Categories
    catFarmersTitle: "शेतकरी",
    catFarmersDesc: "शेती, पीक विमा आणि थेट आर्थिक सहाय्य योजना.",
    catWomenTitle: "महिला कल्याण",
    catWomenDesc: "आर्थिक सहाय्य, लाडकी बहीण आणि महिला सक्षमीकरण योजना.",
    catEducationTitle: "शिक्षण व विद्यार्थी",
    catEducationDesc: "शिष्यवृत्ती, विद्यार्थी सहाय्य आणि उच्च शिक्षण योजना.",
    catHealthcareTitle: "आरोग्य सेवा",
    catHealthcareDesc: "आरोग्य विमा आणि मोफत वैद्यकीय उपचार सहाय्य.",
    catHousingTitle: "घरकुल योजना",
    catHousingDesc: "पक्के घर बांधकाम आणि घरकुल सहाय्य योजना.",
    catEmploymentTitle: "रोजगार व कौशल्य",
    catEmploymentDesc: "रोजगार हमी, कौशल्य विकास आणि सामाजिक सुरक्षा.",
    catBusinessTitle: "लघु व्यवसाय",
    catBusinessDesc: "फेरीवाले, मुद्रा कर्ज आणि व्यवसाय सहाय्य.",

    // Questionnaire
    questionnaireTitlePrefix: "साठी योजना शोधत आहोत",
    questionnaireSubtitle: "चला तुमच्यासाठी उपयुक्त योजना शोधूया. यासाठी फक्त एक मिनिट लागेल.",
    stepIndicator: "टप्पा {current} / {total}",
    backButton: "← मागे जा",
    continueButton: "पुढे चला →",
    submitButton: "उपयुक्त योजना पहा 🎯",
    findingSchemesLoading: "तुमच्यासाठी योग्य योजना शोधत आहोत...",
    selectOptionPrompt: "कृपया पुढे जाण्यासाठी एक पर्याय निवडा.",

    // Questionnaire Common Questions
    ageQuestion: "तुमचे वय किती आहे?",
    agePlaceholder: "तुमचे वय टाका (उदा. 35)",
    ageError: "कृपया 10 ते 120 वर्षांच्या दरम्यान योग्य वय टाका.",
    stateQuestion: "तुम्ही कुठे राहता?",
    statePlaceholder: "-- आपले राज्य निवडा --",
    stateError: "कृपया यादीतून आपले राज्य निवडा.",
    incomeQuestion: "तुमच्या कुटुंबाचे अंदाजे वार्षिक उत्पन्न किती आहे?",
    incomeBelow25: "₹2.5 लाखांपेक्षा कमी",
    income25to6: "₹2.5 लाख ते ₹6 लाख",
    incomeAbove6: "₹6 लाखांपेक्षा जास्त",
    incomeDontKnow: "माहित नाही / सांगायचे नाही",

    // Social Category Questions
    socialCategoryQuestion: "तुम्ही कोणत्या सामाजिक प्रवर्गातील आहात?",
    socialCatGeneral: "खुला प्रवर्ग (General)",
    socialCatSC: "अनुसूचित जाती (SC)",
    socialCatST: "अनुसूचित जमाती (ST)",
    socialCatOBC: "इतर मागासवर्गीय (OBC)",
    socialCatEBC: "आर्थिकदृष्ट्या मागास वर्ग (EBC)",
    socialCatDNT: "विमुक्त जाती किंवा भटक्या जमाती (DNT / VJNT / NT)",
    socialCatDontKnow: "माहित नाही / सांगायचे नाही",

    // Rural / Urban Area Questions
    areaQuestion: "तुम्ही ग्रामीण भागात राहता की शहरी भागात?",
    areaRural: "ग्रामीण भाग (गाव)",
    areaUrban: "शहरी भाग (शहर / नगर)",
    areaDontKnow: "माहित नाही / खात्री नाही",

    // Farmers Questions
    farmerLandQuestion: "तुमच्या किंवा तुमच्या कुटुंबाच्या नावावर शेतजमीन आहे का?",
    farmerLandYes: "होय, आमच्याकडे शेतजमीन आहे",
    farmerLandNo: "नाही, कुळ / बटाईदार किंवा भूमिहीन आहोत",
    farmerLandDontKnow: "माहित नाही / खात्री नाही",
    farmerNeedQuestion: "तुम्हाला कोणत्या प्रकारची मदत हवी आहे?",
    farmerNeedCropInsurance: "पीक विमा (पिकांच्या नुकसानीपासून संरक्षण)",
    farmerNeedDirectSupport: "थेट आर्थिक मदत (शेतकरी सन्मान निधी)",
    farmerNeedEquipment: "शेती अवजारे आणि खते-बियाणे मदत",
    farmerNeedLoan: "कृषी कर्ज किंवा किसान क्रेडिट कार्ड",

    // Women Questions
    womenStatusQuestion: "तुमची सध्याची परिस्थिती काय आहे?",
    womenStatusMarried: "विवाहित महिला",
    womenStatusUnmarried: "अविवाहित तरुणी / महिला",
    womenStatusPregnant: "गरोदर किंवा स्तनदा माता",
    womenStatusWidow: "विधवा, परित्यक्ता किंवा एकल महिला",
    womenStatusGeneral: "सांगायचे नाही",
    womenNeedQuestion: "तुम्ही कोणत्या प्रकारची मदत शोधत आहात?",
    womenNeedFinance: "महिलांसाठी मासिक आर्थिक मदत (लाडकी बहीण)",
    womenNeedGas: "मोफत गॅस सिलेंडर जोडणी (उज्ज्वला)",
    womenNeedMaternity: "मातृत्व आणि गरोदरपण आर्थिक मदत",
    womenNeedTraining: "कौशल्य प्रशिक्षण आणि स्वयंरोजगार मदत",

    // Education Questions
    eduStatusQuestion: "तुम्ही सध्या विद्यार्थी आहात किंवा शिक्षण घेत आहात का?",
    eduStatusYes: "होय, शाळा किंवा महाविद्यालयात शिकत आहोत",
    eduStatusNo: "नाही, शिक्षण किंवा कौशल्य प्रशिक्षणाची संधी शोधत आहोत",
    eduNeedQuestion: "तुम्हाला कोणत्या प्रकारची शैक्षणिक मदत हवी आहे?",
    eduNeedScholarship: "शालेय किंवा मॅट्रिकपूर्व/मॅट्रिकोत्तर शिष्यवृत्ती",
    eduNeedHigherEdu: "उच्च शिक्षण मदत आणि स्पर्धा परीक्षा कोचिंग",
    eduNeedSkill: "कौशल्य विकास आणि व्यावसायिक प्रमाणपत्र",

    // Healthcare Questions
    healthNeedQuestion: "तुम्हाला कोणत्या प्रकारची आरोग्य सेवा मदत हवी आहे?",
    healthNeedHospital: "रुग्णालयात उपचार आणि शस्त्रक्रिया सहाय्य",
    healthNeedInsurance: "मोफत आरोग्य विमा कार्ड (₹5 लाखांपर्यंत)",
    healthNeedSenior: "ज्येष्ठ नागरिक आरोग्य संरक्षण (वय 70+ वर्ष)",
    healthNeedCritical: "गंभीर आजार किंवा वैद्यकीय उपचार मदत",

    // Housing Questions
    housingPuccaQuestion: "तुमच्या किंवा तुमच्या कुटुंबाकडे पक्के घर आहे का?",
    housingPuccaNo: "नाही, कच्चे घर, तात्पुरते निवारे किंवा भाड्याने राहतो",
    housingPuccaYes: "होय, आमच्याकडे पक्के घर आहे",
    housingPuccaDontKnow: "माहित नाही / खात्री नाही",
    housingAreaQuestion: "तुम्ही घर कुठे बांधण्याची किंवा खरेदी करण्याची योजना आखत आहात?",
    housingAreaRural: "ग्रामीण भागात / गावात (पीएम आवास ग्रामीण)",
    housingAreaUrban: "शहरी भागात / नगरपालिका क्षेत्रात (पीएम आवास शहरी)",

    // Employment Questions
    empStatusQuestion: "तुमची सध्याची रोजगार स्थिती काय आहे?",
    empStatusUnemployed: "बेरोजगार / कामाच्या शोधात",
    empStatusWage: "दैनिक रोजंदारी मजूर / ग्रामीण कामगार",
    empStatusYouth: "कौशल्य प्रशिक्षण घेऊ इच्छिणारा तरुण",
    empStatusUnorganized: "असंघटित क्षेत्रातील कामगार",
    empNeedQuestion: "तुम्हाला कोणत्या प्रकारची रोजगार मदत हवी आहे?",
    empNeedWage: "100 दिवस हमीचे ग्रामीण रोजगार (मनरेगा)",
    empNeedSkill: "मोफत कौशल्य विकास व उद्योग प्रशिक्षण (पीएमकेव्हीवाय)",
    empNeedPension: "वृद्धापकाळ पेन्शन व सामाजिक सुरक्षा (अटल पेन्शन)",
    empNeedAccident: "कमी खर्चात अपघात विमा संरक्षण (सुरक्षा विमा)",

    // Small Business Questions
    bizStatusQuestion: "तुम्ही कोणत्या प्रकारचा व्यवसाय किंवा काम करता?",
    bizStatusVendor: "फेरीवाले / हातगाडी चालक / रस्त्यावरील विक्रेते",
    bizStatusSmallBiz: "लहान व्यवसाय / किरकोळ दुकानदार",
    bizStatusSelf: "सूक्ष्म उद्योजक / स्वयंरोजगार",
    bizStatusAspiring: "नवीन लहान व्यवसाय सुरू करण्याची योजना",
    bizNeedQuestion: "तुम्हाला कोणत्या प्रकारची आर्थिक मदत हवी आहे?",
    bizNeedWorkingCap: "विनातारण खेळते भांडवल कर्ज (पीएम स्वनिधी ₹50,000 पर्यंत)",
    bizNeedMudra: "सूक्ष्म उद्योगासाठी व्यवसाय कर्ज (मुद्रा कर्ज ₹10 लाखांपर्यंत)",
    bizNeedBank: "झिरो-बॅलन्स बँक खाते, ओव्हरड्राफ्ट व विमा (जन धन)",

    // Results Page
    resultsTitle: "तुमच्यासाठी उपयुक्त ठरू शकणाऱ्या योजना",
    resultsCountPrefix: "तुम्ही दिलेल्या माहितीच्या आधारे आम्हाला",
    resultsCountSuffix: "योजना सापडल्या आहेत.",
    noticeLabel: "सूचना:",
    disclaimerText: "दिलेल्या माहितीच्या आधारे या योजना संभाव्यतः उपयुक्त असू शकतात. अंतिम पात्रता संबंधित सरकारी प्राधिकरणाद्वारे निश्चित केली जाते.",
    noResultsTitle: "दिलेल्या माहितीशी जुळणाऱ्या योजना सापडल्या नाहीत",
    noResultsText: "तुम्ही दिलेल्या माहितीच्या आधारे या प्रवर्गात थेट जुळणाऱ्या योजना सापडल्या नाहीत. कृपया उत्तरे बदलून पुन्हा प्रयत्न करा.",
    changeAnswers: "उत्तरे बदला",
    startNewSearch: "नवीन शोध सुरू करा",

    // Scheme Card
    matchRelevance: "सुसंगतता गुण:",
    whyRelevant: "ही योजना तुमच्यासाठी का उपयुक्त ठरू शकते",
    infoNeeded: "आवश्यक कागदपत्रे व माहिती",
    viewDetails: "योजनेचा तपशील पहा",
    hideDetails: "तपशील लपवा",

    // Dynamic Reason Codes
    reason_ALL_INDIA_AVAILABLE: "संपूर्ण भारतात लागू, ज्यामध्ये {state} चा समावेश आहे",
    reason_STATE_SPECIFIC_MATCH: "विशेषतः {state} च्या रहिवाशांसाठी उपलब्ध",
    reason_TARGET_GROUP_FARMER: "शेतकरी आणि ग्रामीण नागरिकांसाठी उपयुक्त",
    reason_TARGET_GROUP_STUDENT: "विद्यार्थी आणि तरुणांसाठी उपयुक्त",
    reason_TARGET_GROUP_WOMEN: "महिलांसाठी विशेष साहाय्य पुरवते",
    reason_TARGET_GROUP_BUSINESS: "लहान व्यवसाय, फेरीवाले आणि नवउद्योजकांसाठी उपयुक्त",
    reason_TARGET_GROUP_WORKER: "असंघटित आणि अकुशल कामगारांसाठी उपयुक्त",
    reason_NEED_MATCH: "तुमच्या निवडलेल्या गरजेनुसार सुसंगत",
    reason_AGE_CRITERIA_MATCH: "तुमचे वय ({age} वर्षे) योजनेच्या अटींशी जुळणारे आहे",
    reason_INCOME_CRITERIA_MATCH: "तुमचे उत्पन्न योजनेच्या निकषांतर्गत आहे",
    reason_LAND_OWNERSHIP_MATCH: "तुमच्या शेतजमीन मालकी हक्काशी जुळणारे",
    reason_SOCIAL_CATEGORY_MATCH: "तुमच्या सामाजिक प्रवर्गाशी ({category}) सुसंगत",
    reason_AREA_MATCH: "विशेषतः {area} भागासाठी तयार केलेली",
    reason_HOUSING_NEED_MATCH: "पक्के घर नसलेल्या कुटुंबांसाठी उपयुक्त",

    // Scheme Detail Modal
    modalTitle: "योजनेचा संपूर्ण तपशील",
    departmentLabel: "विभाग / मंत्रालय:",
    aboutLabel: "योजनेबद्दल",
    benefitsLabel: "मुख्य फायदे",
    documentsLabel: "आवश्यक कागदपत्रे व माहिती",
    applyButton: "अर्ज करा / अधिक माहिती ↗",
    sourceButton: "अधिकृत संकेतस्थळ ↗",
    closeModal: "बंद करा",
    loadingDetails: "सत्यापित योजनेची माहिती लोड होत आहे...",

    // Errors
    errorTitle: "सध्या तुमच्यासाठी योजना शोधता आल्या नाहीत.",
    errorGeneric: "योजना शोधताना अनपेक्षित अडचण आली. कृपया पुन्हा प्रयत्न करा.",
    errorNetwork: "सर्व्हरशी संपर्क होऊ शकला नाही. कृपया इंटरनेट कनेक्शन किंवा बॅकएंड तपासा.",
    tryAgain: "पुन्हा प्रयत्न करा",
    startOver: "सुरुवातीपासून करा",
  },
};

/**
 * Helper to get localized string with fallback to English.
 * @param {string} lang - Current language code ('en', 'hi', 'mr')
 * @param {string} key - String identifier key
 * @param {object} params - Optional replacements (e.g. { current: 1, total: 4 })
 * @returns {string} - Localized string
 */
export function getLocaleString(lang, key, params = {}) {
  const langDict = STRINGS[lang] || STRINGS.en;
  let text = langDict[key] || STRINGS.en[key] || key;
  if (params && typeof text === 'string') {
    Object.keys(params).forEach((paramKey) => {
      text = text.replaceAll(`{${paramKey}}`, params[paramKey]);
    });
  }
  return text;
}

export const CURRENT_LANG = "en";
export const t = (key, params) => getLocaleString(CURRENT_LANG, key, params);
