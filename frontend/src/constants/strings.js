/**
 * Centralized UI strings for YojnaSathi frontend.
 * Structured to support seamless localization (English, Hindi, Marathi)
 * without touching component code.
 */
export const STRINGS = {
  en: {
    appTitle: "YojnaSathi",
    appSubtitle: "Find government schemes that may be relevant to you",
    newConversation: "New Chat",
    resetAriaLabel: "Start a new conversation and clear current profile",

    // Welcome Screen
    welcomeTitle: "How can YojnaSathi help you today?",
    welcomeSubtitle: "Describe your situation in simple words, or choose one of the common topics below to get started.",
    suggestionsLabel: "Suggested topics:",
    suggestions: [
      {
        id: "farmer",
        icon: "🌾",
        label: "I'm a farmer looking for crop assistance",
        message: "I am a farmer from Maharashtra and I need crop insurance assistance",
      },
      {
        id: "student",
        icon: "🎓",
        label: "I need a student scholarship",
        message: "I am a student looking for scholarship schemes for higher education",
      },
      {
        id: "health",
        icon: "🏥",
        label: "I need healthcare support",
        message: "I need healthcare and medical treatment financial assistance",
      },
      {
        id: "housing",
        icon: "🏠",
        label: "I need housing assistance",
        message: "I need financial assistance to construct or buy a pucca house",
      },
      {
        id: "employment",
        icon: "💼",
        label: "I want employment or skill training",
        message: "I am looking for employment guarantee or skill training programs",
      },
      {
        id: "business",
        icon: "💰",
        label: "I need help for my small business",
        message: "I need a collateral-free loan or working capital for my small business",
      },
    ],

    // Chat Input
    inputPlaceholder: "Describe your situation (e.g., 'I am a 35 year old farmer in Maharashtra...')",
    sendButtonLabel: "Send",
    sendButtonAriaLabel: "Send your message to YojnaSathi",
    loadingText: "Searching relevant government schemes...",

    // Scheme Card
    matchRelevance: "Match relevance:",
    whyRelevant: "Why this may be relevant",
    infoNeeded: "Information you may need",
    viewDetails: "View Scheme Details",
    hideDetails: "Hide Details",
    loadingDetails: "Loading scheme details...",
    departmentLabel: "Department:",
    benefitsLabel: "Key Benefits:",
    applyButton: "Apply / Learn more",
    sourceButton: "Official source",
    noDetailsAvailable: "Full details currently unavailable.",

    // Errors
    errorBadRequest: "Please enter a valid message describing your situation or need.",
    errorServiceUnavailable: "Our AI assistant is currently being configured. Please ensure the backend server has the GEMINI_API_KEY set.",
    errorBadGateway: "The AI service encountered a temporary issue. Please try sending your message again.",
    errorNetwork: "Unable to connect to the YojnaSathi server. Please check your internet connection or verify the backend is running.",
    errorGeneric: "An unexpected error occurred. Please try again.",
    retryButton: "Try Again",
  },
  hi: {
    appTitle: "योजनासाथी",
    appSubtitle: "आपके लिए प्रासंगिक सरकारी योजनाएं खोजें",
    newConversation: "नई बातचीत",
  },
  mr: {
    appTitle: "योजनासाथी",
    appSubtitle: "तुमच्यासाठी उपयुक्त सरकारी योजना शोधा",
    newConversation: "नवीन संभाषण",
  },
};

// Default language
export const CURRENT_LANG = "en";
export const t = (key) => STRINGS[CURRENT_LANG][key] || STRINGS.en[key] || key;
