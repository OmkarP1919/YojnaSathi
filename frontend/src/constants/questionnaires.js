/**
 * Definitions for categories, questionnaire steps, and Indian States/UTs.
 * Every step maps strictly to fields supported by backend's CitizenProfile:
 * age, gender, state, occupation, annual_income, is_student, is_farmer,
 * marital_status, owns_land, owns_house, needs.
 */

export const INDIAN_STATES = [
  { value: "maharashtra", labels: { en: "Maharashtra", hi: "महाराष्ट्र", mr: "महाराष्ट्र" } },
  { value: "andhra pradesh", labels: { en: "Andhra Pradesh", hi: "आंध्र प्रदेश", mr: "आंध्र प्रदेश" } },
  { value: "arunachal pradesh", labels: { en: "Arunachal Pradesh", hi: "अरुणाचल प्रदेश", mr: "अरुणाचल प्रदेश" } },
  { value: "assam", labels: { en: "Assam", hi: "असम", mr: "आसाम" } },
  { value: "bihar", labels: { en: "Bihar", hi: "बिहार", mr: "बिहार" } },
  { value: "chhattisgarh", labels: { en: "Chhattisgarh", hi: "छत्तीसगढ़", mr: "छत्तीसगड" } },
  { value: "goa", labels: { en: "Goa", hi: "गोवा", mr: "गोवा" } },
  { value: "gujarat", labels: { en: "Gujarat", hi: "गुजरात", mr: "गुजरात" } },
  { value: "haryana", labels: { en: "Haryana", hi: "हरियाणा", mr: "हरियाणा" } },
  { value: "himachal pradesh", labels: { en: "Himachal Pradesh", hi: "हिमाचल प्रदेश", mr: "हिमाचल प्रदेश" } },
  { value: "jharkhand", labels: { en: "Jharkhand", hi: "झारखंड", mr: "झारखंड" } },
  { value: "karnataka", labels: { en: "Karnataka", hi: "कर्नाटक", mr: "कर्नाटक" } },
  { value: "kerala", labels: { en: "Kerala", hi: "केरल", mr: "केरळ" } },
  { value: "madhya pradesh", labels: { en: "Madhya Pradesh", hi: "मध्य प्रदेश", mr: "मध्य प्रदेश" } },
  { value: "manipur", labels: { en: "Manipur", hi: "मणिपुर", mr: "मणिपूर" } },
  { value: "meghalaya", labels: { en: "Meghalaya", hi: "मेघालय", mr: "मेघालय" } },
  { value: "mizoram", labels: { en: "Mizoram", hi: "मिज़ोरम", mr: "मिझोराम" } },
  { value: "nagaland", labels: { en: "Nagaland", hi: "नागालैंड", mr: "नागालँड" } },
  { value: "odisha", labels: { en: "Odisha", hi: "ओडिशा", mr: "ओडिशा" } },
  { value: "punjab", labels: { en: "Punjab", hi: "पंजाब", mr: "पंजाब" } },
  { value: "rajasthan", labels: { en: "Rajasthan", hi: "राजस्थान", mr: "राजस्थान" } },
  { value: "sikkim", labels: { en: "Sikkim", hi: "सिक्किम", mr: "सिक्कीम" } },
  { value: "tamil nadu", labels: { en: "Tamil Nadu", hi: "तमिलनाडु", mr: "तमिळनाडू" } },
  { value: "telangana", labels: { en: "Telangana", hi: "तेलंगाना", mr: "तेलंगणा" } },
  { value: "tripura", labels: { en: "Tripura", hi: "त्रिपुरा", mr: "त्रिपुरा" } },
  { value: "uttar pradesh", labels: { en: "Uttar Pradesh", hi: "उत्तर प्रदेश", mr: "उत्तर प्रदेश" } },
  { value: "uttarakhand", labels: { en: "Uttarakhand", hi: "उत्तराखंड", mr: "उत्तराखंड" } },
  { value: "west bengal", labels: { en: "West Bengal", hi: "पश्चिम बंगाल", mr: "पश्चिम बंगाल" } },
  { value: "andaman and nicobar islands", labels: { en: "Andaman and Nicobar Islands", hi: "अंडमान और निकोबार द्वीप समूह", mr: "अंदमान आणि निकोबार बेटे" } },
  { value: "chandigarh", labels: { en: "Chandigarh", hi: "चंडीगढ़", mr: "चंदिगढ" } },
  { value: "dadra and nagar haveli and daman and diu", labels: { en: "Dadra and Nagar Haveli and Daman and Diu", hi: "दादरा और नगर हवेली एवं दमन और दीव", mr: "दादरा आणि नगर हवेली आणि दमण आणि दीव" } },
  { value: "delhi", labels: { en: "Delhi (NCT)", hi: "दिल्ली (एनसीटी)", mr: "दिल्ली (एनसीटी)" } },
  { value: "jammu and kashmir", labels: { en: "Jammu and Kashmir", hi: "जम्मू और कश्मीर", mr: "जम्मू आणि काश्मीर" } },
  { value: "ladakh", labels: { en: "Ladakh", hi: "लद्दाख", mr: "लडाख" } },
  { value: "lakshadweep", labels: { en: "Lakshadweep", hi: "लक्षद्वीप", mr: "लक्षद्वीप" } },
  { value: "puducherry", labels: { en: "Puducherry", hi: "पुडुचेरी", mr: "पुडुचेरी" } }
];

const stateStepOptions = INDIAN_STATES.map((s) => ({
  value: s.value,
  labels: s.labels,
}));

export const CATEGORIES = [
  {
    id: "farmers",
    icon: "🌾",
    titleKey: "catFarmersTitle",
    descKey: "catFarmersDesc",
    initialProfile: {
      is_farmer: true,
      occupation: "farmer",
    },
    steps: [
      {
        id: "age",
        type: "number",
        questionKey: "ageQuestion",
        placeholderKey: "agePlaceholder",
        errorKey: "ageError",
        field: "age",
        min: 10,
        max: 120,
      },
      {
        id: "state",
        type: "select",
        questionKey: "stateQuestion",
        placeholderKey: "statePlaceholder",
        errorKey: "stateError",
        field: "state",
        options: stateStepOptions,
      },
      {
        id: "farmer_land",
        type: "single_choice",
        questionKey: "farmerLandQuestion",
        field: "owns_land",
        options: [
          {
            value: true,
            labelKey: "farmerLandYes",
            profilePatch: { owns_land: true },
          },
          {
            value: false,
            labelKey: "farmerLandNo",
            profilePatch: { owns_land: false },
          },
          {
            value: "unknown",
            labelKey: "farmerLandDontKnow",
            profilePatch: { owns_land: null },
          },
        ],
      },
      {
        id: "farmer_need",
        type: "single_choice",
        questionKey: "farmerNeedQuestion",
        field: "needs",
        options: [
          {
            value: "crop insurance",
            labelKey: "farmerNeedCropInsurance",
            profilePatch: { needs: ["crop insurance"] },
          },
          {
            value: "farming",
            labelKey: "farmerNeedDirectSupport",
            profilePatch: { needs: ["farming"] },
          },
          {
            value: "agriculture",
            labelKey: "farmerNeedEquipment",
            profilePatch: { needs: ["agriculture"] },
          },
          {
            value: "loan",
            labelKey: "farmerNeedLoan",
            profilePatch: { needs: ["loan"] },
          },
        ],
      },
    ],
  },

  {
    id: "women",
    icon: "👩",
    titleKey: "catWomenTitle",
    descKey: "catWomenDesc",
    initialProfile: {
      gender: "female",
    },
    steps: [
      {
        id: "age",
        type: "number",
        questionKey: "ageQuestion",
        placeholderKey: "agePlaceholder",
        errorKey: "ageError",
        field: "age",
        min: 10,
        max: 120,
      },
      {
        id: "state",
        type: "select",
        questionKey: "stateQuestion",
        placeholderKey: "statePlaceholder",
        errorKey: "stateError",
        field: "state",
        options: stateStepOptions,
      },
      {
        id: "income",
        type: "single_choice",
        questionKey: "incomeQuestion",
        field: "annual_income",
        options: [
          {
            value: 200000,
            labelKey: "incomeBelow25",
            profilePatch: { annual_income: 200000 },
          },
          {
            value: 400000,
            labelKey: "income25to6",
            profilePatch: { annual_income: 400000 },
          },
          {
            value: 800000,
            labelKey: "incomeAbove6",
            profilePatch: { annual_income: 800000 },
          },
          {
            value: null,
            labelKey: "incomeDontKnow",
            profilePatch: { annual_income: null },
          },
        ],
      },
      {
        id: "women_status",
        type: "single_choice",
        questionKey: "womenStatusQuestion",
        field: "marital_status",
        options: [
          {
            value: "married",
            labelKey: "womenStatusMarried",
            profilePatch: { marital_status: "married" },
          },
          {
            value: "unmarried",
            labelKey: "womenStatusUnmarried",
            profilePatch: { marital_status: "unmarried" },
          },
          {
            value: "pregnant",
            labelKey: "womenStatusPregnant",
            profilePatch: { marital_status: "married", needs: ["pregnancy"] },
          },
          {
            value: "widow",
            labelKey: "womenStatusWidow",
            profilePatch: { marital_status: "widow" },
          },
          {
            value: "general",
            labelKey: "womenStatusGeneral",
            profilePatch: { marital_status: null },
          },
        ],
      },
      {
        id: "women_need",
        type: "single_choice",
        questionKey: "womenNeedQuestion",
        field: "needs",
        options: [
          {
            value: "financial assistance for women",
            labelKey: "womenNeedFinance",
            profilePatch: { needs: ["financial assistance for women"] },
          },
          {
            value: "cooking gas",
            labelKey: "womenNeedGas",
            profilePatch: { needs: ["cooking gas"] },
          },
          {
            value: "maternity",
            labelKey: "womenNeedMaternity",
            profilePatch: { needs: ["maternity"] },
          },
          {
            value: "women",
            labelKey: "womenNeedTraining",
            profilePatch: { needs: ["women"] },
          },
        ],
      },
    ],
  },

  {
    id: "education",
    icon: "🎓",
    titleKey: "catEducationTitle",
    descKey: "catEducationDesc",
    initialProfile: {
      is_student: true,
      occupation: "student",
    },
    steps: [
      {
        id: "age",
        type: "number",
        questionKey: "ageQuestion",
        placeholderKey: "agePlaceholder",
        errorKey: "ageError",
        field: "age",
        min: 10,
        max: 120,
      },
      {
        id: "state",
        type: "select",
        questionKey: "stateQuestion",
        placeholderKey: "statePlaceholder",
        errorKey: "stateError",
        field: "state",
        options: stateStepOptions,
      },
      {
        id: "edu_need",
        type: "single_choice",
        questionKey: "eduNeedQuestion",
        field: "needs",
        options: [
          {
            value: "scholarship",
            labelKey: "eduNeedScholarship",
            profilePatch: { needs: ["scholarship"] },
          },
          {
            value: "education",
            labelKey: "eduNeedHigherEdu",
            profilePatch: { needs: ["education"] },
          },
          {
            value: "skill",
            labelKey: "eduNeedSkill",
            profilePatch: { needs: ["skill"] },
          },
        ],
      },
      {
        id: "income",
        type: "single_choice",
        questionKey: "incomeQuestion",
        field: "annual_income",
        options: [
          {
            value: 200000,
            labelKey: "incomeBelow25",
            profilePatch: { annual_income: 200000 },
          },
          {
            value: 400000,
            labelKey: "income25to6",
            profilePatch: { annual_income: 400000 },
          },
          {
            value: 800000,
            labelKey: "incomeAbove6",
            profilePatch: { annual_income: 800000 },
          },
          {
            value: null,
            labelKey: "incomeDontKnow",
            profilePatch: { annual_income: null },
          },
        ],
      },
      {
        id: "social_category",
        type: "single_choice",
        questionKey: "socialCategoryQuestion",
        field: "social_category",
        showWhen: (profile) => !profile.needs || profile.needs.includes("scholarship") || profile.needs.includes("education"),
        options: [
          {
            value: "general",
            labelKey: "socialCatGeneral",
            profilePatch: { social_category: "general" },
          },
          {
            value: "sc",
            labelKey: "socialCatSC",
            profilePatch: { social_category: "sc" },
          },
          {
            value: "st",
            labelKey: "socialCatST",
            profilePatch: { social_category: "st" },
          },
          {
            value: "obc",
            labelKey: "socialCatOBC",
            profilePatch: { social_category: "obc" },
          },
          {
            value: "ebc",
            labelKey: "socialCatEBC",
            profilePatch: { social_category: "ebc" },
          },
          {
            value: "dnt",
            labelKey: "socialCatDNT",
            profilePatch: { social_category: "dnt" },
          },
          {
            value: "unknown",
            labelKey: "socialCatDontKnow",
            profilePatch: { social_category: null },
          },
        ],
      },
    ],
  },

  {
    id: "healthcare",
    icon: "🏥",
    titleKey: "catHealthcareTitle",
    descKey: "catHealthcareDesc",
    initialProfile: {},
    steps: [
      {
        id: "age",
        type: "number",
        questionKey: "ageQuestion",
        placeholderKey: "agePlaceholder",
        errorKey: "ageError",
        field: "age",
        min: 10,
        max: 120,
      },
      {
        id: "state",
        type: "select",
        questionKey: "stateQuestion",
        placeholderKey: "statePlaceholder",
        errorKey: "stateError",
        field: "state",
        options: stateStepOptions,
      },
      {
        id: "income",
        type: "single_choice",
        questionKey: "incomeQuestion",
        field: "annual_income",
        options: [
          {
            value: 200000,
            labelKey: "incomeBelow25",
            profilePatch: { annual_income: 200000 },
          },
          {
            value: 400000,
            labelKey: "income25to6",
            profilePatch: { annual_income: 400000 },
          },
          {
            value: 800000,
            labelKey: "incomeAbove6",
            profilePatch: { annual_income: 800000 },
          },
          {
            value: null,
            labelKey: "incomeDontKnow",
            profilePatch: { annual_income: null },
          },
        ],
      },
      {
        id: "health_need",
        type: "single_choice",
        questionKey: "healthNeedQuestion",
        field: "needs",
        options: [
          {
            value: "hospital",
            labelKey: "healthNeedHospital",
            profilePatch: { needs: ["hospital"] },
          },
          {
            value: "health",
            labelKey: "healthNeedInsurance",
            profilePatch: { needs: ["health"] },
          },
          {
            value: "senior_health",
            labelKey: "healthNeedSenior",
            profilePatch: { needs: ["health"] },
          },
          {
            value: "treatment",
            labelKey: "healthNeedCritical",
            profilePatch: { needs: ["treatment"] },
          },
        ],
      },
    ],
  },

  {
    id: "housing",
    icon: "🏠",
    titleKey: "catHousingTitle",
    descKey: "catHousingDesc",
    initialProfile: {},
    steps: [
      {
        id: "age",
        type: "number",
        questionKey: "ageQuestion",
        placeholderKey: "agePlaceholder",
        errorKey: "ageError",
        field: "age",
        min: 18,
        max: 120,
      },
      {
        id: "state",
        type: "select",
        questionKey: "stateQuestion",
        placeholderKey: "statePlaceholder",
        errorKey: "stateError",
        field: "state",
        options: stateStepOptions,
      },
      {
        id: "income",
        type: "single_choice",
        questionKey: "incomeQuestion",
        field: "annual_income",
        options: [
          {
            value: 250000,
            labelKey: "incomeBelow25",
            profilePatch: { annual_income: 250000 },
          },
          {
            value: 500000,
            labelKey: "income25to6",
            profilePatch: { annual_income: 500000 },
          },
          {
            value: 800000,
            labelKey: "incomeAbove6",
            profilePatch: { annual_income: 800000 },
          },
          {
            value: null,
            labelKey: "incomeDontKnow",
            profilePatch: { annual_income: null },
          },
        ],
      },
      {
        id: "housing_pucca",
        type: "single_choice",
        questionKey: "housingPuccaQuestion",
        field: "owns_house",
        options: [
          {
            value: false,
            labelKey: "housingPuccaNo",
            profilePatch: { owns_house: false },
          },
          {
            value: true,
            labelKey: "housingPuccaYes",
            profilePatch: { owns_house: true },
          },
          {
            value: "unknown",
            labelKey: "housingPuccaDontKnow",
            profilePatch: { owns_house: null },
          },
        ],
      },
      {
        id: "housing_area",
        type: "single_choice",
        questionKey: "housingAreaQuestion",
        field: "rural_or_urban",
        options: [
          {
            value: "rural",
            labelKey: "housingAreaRural",
            profilePatch: { rural_or_urban: "rural", needs: ["housing", "pucca"] },
          },
          {
            value: "urban",
            labelKey: "housingAreaUrban",
            profilePatch: { rural_or_urban: "urban", needs: ["housing", "awas"] },
          },
          {
            value: "unknown",
            labelKey: "areaDontKnow",
            profilePatch: { rural_or_urban: null, needs: ["housing"] },
          },
        ],
      },
    ],
  },

  {
    id: "employment",
    icon: "💼",
    titleKey: "catEmploymentTitle",
    descKey: "catEmploymentDesc",
    initialProfile: {},
    steps: [
      {
        id: "age",
        type: "number",
        questionKey: "ageQuestion",
        placeholderKey: "agePlaceholder",
        errorKey: "ageError",
        field: "age",
        min: 15,
        max: 120,
      },
      {
        id: "state",
        type: "select",
        questionKey: "stateQuestion",
        placeholderKey: "statePlaceholder",
        errorKey: "stateError",
        field: "state",
        options: stateStepOptions,
      },
      {
        id: "emp_status",
        type: "single_choice",
        questionKey: "empStatusQuestion",
        field: "occupation",
        options: [
          {
            value: "unemployed",
            labelKey: "empStatusUnemployed",
            profilePatch: { occupation: "unemployed" },
          },
          {
            value: "laborer",
            labelKey: "empStatusWage",
            profilePatch: { occupation: "laborer" },
          },
          {
            value: "youth",
            labelKey: "empStatusYouth",
            profilePatch: { occupation: "youth" },
          },
          {
            value: "worker",
            labelKey: "empStatusUnorganized",
            profilePatch: { occupation: "worker" },
          },
        ],
      },
      {
        id: "emp_need",
        type: "single_choice",
        questionKey: "empNeedQuestion",
        field: "needs",
        options: [
          {
            value: "wage_employment",
            labelKey: "empNeedWage",
            profilePatch: { needs: ["mgnrega", "employment"] },
          },
          {
            value: "skill_training",
            labelKey: "empNeedSkill",
            profilePatch: { needs: ["skill", "training"] },
          },
          {
            value: "pension",
            labelKey: "empNeedPension",
            profilePatch: { needs: ["pension"] },
          },
          {
            value: "accident_insurance",
            labelKey: "empNeedAccident",
            profilePatch: { needs: ["accident insurance"] },
          },
        ],
      },
    ],
  },

  {
    id: "business",
    icon: "🏪",
    titleKey: "catBusinessTitle",
    descKey: "catBusinessDesc",
    initialProfile: {},
    steps: [
      {
        id: "age",
        type: "number",
        questionKey: "ageQuestion",
        placeholderKey: "agePlaceholder",
        errorKey: "ageError",
        field: "age",
        min: 18,
        max: 120,
      },
      {
        id: "state",
        type: "select",
        questionKey: "stateQuestion",
        placeholderKey: "statePlaceholder",
        errorKey: "stateError",
        field: "state",
        options: stateStepOptions,
      },
      {
        id: "biz_status",
        type: "single_choice",
        questionKey: "bizStatusQuestion",
        field: "occupation",
        options: [
          {
            value: "street vendor",
            labelKey: "bizStatusVendor",
            profilePatch: { occupation: "street vendor" },
          },
          {
            value: "small business",
            labelKey: "bizStatusSmallBiz",
            profilePatch: { occupation: "small business" },
          },
          {
            value: "self-employed",
            labelKey: "bizStatusSelf",
            profilePatch: { occupation: "self-employed" },
          },
          {
            value: "entrepreneur",
            labelKey: "bizStatusAspiring",
            profilePatch: { occupation: "entrepreneur" },
          },
        ],
      },
      {
        id: "biz_need",
        type: "single_choice",
        questionKey: "bizNeedQuestion",
        field: "needs",
        options: [
          {
            value: "working_capital",
            labelKey: "bizNeedWorkingCap",
            profilePatch: { needs: ["working capital", "loan"] },
          },
          {
            value: "mudra_loan",
            labelKey: "bizNeedMudra",
            profilePatch: { needs: ["business", "loan"] },
          },
          {
            value: "banking",
            labelKey: "bizNeedBank",
            profilePatch: { needs: ["banking"] },
          },
        ],
      },
    ],
  },
];

/**
 * Filter steps dynamically based on current CitizenProfile state.
 * Steps with a `showWhen` function are evaluated conditionally.
 */
export function getActiveSteps(category, profile = {}) {
  if (!category || !category.steps) return [];
  return category.steps.filter((step) => {
    if (typeof step.showWhen === 'function') {
      return step.showWhen(profile);
    }
    return true;
  });
}

