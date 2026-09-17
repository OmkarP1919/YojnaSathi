import React, { useEffect, useState } from 'react';
import Header from './components/Header';
import GatewayHero from './components/GatewayHero';
import Questionnaire from './components/Questionnaire';
import ResultsView from './components/ResultsView';
import SchemeDetailModal from './components/SchemeDetailModal';
import VoiceAssistantView from './components/VoiceAssistant/VoiceAssistantView';
import { getRecommendations, checkBackendHealth } from './api';
import { useApplicationOptions } from './hooks/useApplicationOptions';
import { DEFAULT_LANGUAGE } from './constants/languages';
import { getLocaleString } from './constants/strings';
import { getActiveSteps } from './constants/questionnaires';

function App() {
  const [lang, setLang] = useState(DEFAULT_LANGUAGE);
  const [currentView, setCurrentView] = useState('home'); // 'home' | 'questionnaire' | 'loading' | 'results'
  const [selectedCategory, setSelectedCategory] = useState(null);
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [answers, setAnswers] = useState({});
  const [profile, setProfile] = useState({});
  const [results, setResults] = useState([]);
  const [disclaimer, setDisclaimer] = useState('');
  const [errorKey, setErrorKey] = useState(null);
  const [errorCustomMessage, setErrorCustomMessage] = useState(null);
  const [detailModal, setDetailModal] = useState({ isOpen: false, schemeId: null, schemeName: '' });
  const [voiceOpenSignal, setVoiceOpenSignal] = useState(0);

  useEffect(() => {
    checkBackendHealth().catch(() => {});
  }, []);

  // Lazily fetch physical application centers for displayed results via the
  // existing GET /api/application-options endpoint. Kept out of /api/recommend
  // so recommendations stay fast; results are cached and concurrency-limited.
  const resultSchemeIds = results.map((matchResult) => matchResult?.scheme?.id).filter(Boolean);
  const shouldLoadLocations = (
    profile?.state === 'maharashtra'
    && Boolean(profile?.district)
    && profile.district !== 'other'
  );
  const locationOptions = useApplicationOptions(
    resultSchemeIds,
    {
      state: profile?.state,
      district: profile?.district,
      taluka: profile?.taluka,
    },
    shouldLoadLocations,
  );

  // Reset all search state back to Home
  const handleReset = () => {
    setCurrentView('home');
    setSelectedCategory(null);
    setCurrentStepIndex(0);
    setAnswers({});
    setProfile({});
    setResults([]);
    setDisclaimer('');
    setErrorKey(null);
    setErrorCustomMessage(null);
    setDetailModal({ isOpen: false, schemeId: null, schemeName: '' });
  };

  // Open the existing floating voice assistant from the homepage gateway.
  const handleOpenVoice = () => {
    setVoiceOpenSignal((prev) => prev + 1);
  };

  // Start guided questionnaire for selected category
  const handleSelectCategory = (cat) => {
    setSelectedCategory(cat);
    setCurrentStepIndex(0);
    setAnswers({});
    // Initialize profile only with the category's verified initial fields
    setProfile({ ...(cat.initialProfile || {}) });
    setErrorKey(null);
    setErrorCustomMessage(null);
    setCurrentView('questionnaire');
  };

  // Record user answer and update CitizenProfile patch
  const handleAnswerChange = (stepId, value, profilePatch) => {
    setAnswers((prev) => {
      const updated = {
        ...prev,
        [stepId]: value,
      };
      if (stepId === 'state') {
        delete updated.district;
        delete updated.taluka;
      } else if (stepId === 'district') {
        delete updated.taluka;
      }
      return updated;
    });

    setProfile((prev) => {
      const updated = {
        ...prev,
        ...(profilePatch || {}),
      };
      if (stepId === 'state') {
        delete updated.district;
        delete updated.taluka;
      } else if (stepId === 'district') {
        delete updated.taluka;
      }
      return updated;
    });
  };

  // Next step in questionnaire
  const handleNext = () => {
    if (selectedCategory) {
      const activeSteps = getActiveSteps(selectedCategory, profile);
      if (currentStepIndex < activeSteps.length - 1) {
        setCurrentStepIndex((prev) => prev + 1);
      }
    }
  };

  // Previous step in questionnaire
  const handleBack = () => {
    if (currentStepIndex > 0) {
      setCurrentStepIndex((prev) => prev - 1);
    } else {
      setCurrentView('home');
    }
  };

  // Return to questionnaire from results to tweak answers
  const handleChangeAnswers = () => {
    if (selectedCategory) {
      const activeSteps = getActiveSteps(selectedCategory, profile);
      setCurrentStepIndex(activeSteps.length - 1);
      setCurrentView('questionnaire');
    } else {
      setCurrentView('home');
    }
  };

  // Submit profile to POST /api/recommend
  const handleSubmitQuestionnaire = async () => {
    setCurrentView('loading');
    setErrorKey(null);
    setErrorCustomMessage(null);

    try {
      const submitProfile = { ...profile };
      // Clean up sentinel values so backend receives clean optional fields
      if (submitProfile.district === 'other' || !submitProfile.district) {
        delete submitProfile.district;
        delete submitProfile.taluka;
      } else if (submitProfile.taluka === 'other' || !submitProfile.taluka) {
        delete submitProfile.taluka;
      }
      const response = await getRecommendations(submitProfile, selectedCategory?.id);
      setResults(response.results || []);
      setDisclaimer(response.disclaimer || '');
      setCurrentView('results');
    } catch (err) {
      if (err.request && !err.response) {
        setErrorKey('errorNetwork');
      } else if (err.response?.data?.detail) {
        setErrorCustomMessage(String(err.response.data.detail));
      } else {
        setErrorKey('errorGeneric');
      }
      setCurrentView('results');
    }
  };

  // Open scheme detail modal (triggers GET /api/schemes/{id})
  const handleViewDetails = (schemeId, schemeName, schemeData = null) => {
    setDetailModal({
      isOpen: true,
      schemeId,
      schemeName,
      schemeData,
    });
  };

  const handleCloseDetails = () => {
    setDetailModal({
      isOpen: false,
      schemeId: null,
      schemeName: '',
      schemeData: null,
    });
  };

  const activeError = errorCustomMessage || (errorKey ? getLocaleString(lang, errorKey) : null);

  return (
    <div className="app-layout">
      <Header
        currentView={currentView}
        onReset={handleReset}
        lang={lang}
        onLanguageChange={setLang}
      />

      <main className="main-content" role="main">
        {/* VIEW 1: Home / Three Gateways + Quick Topics */}
        {currentView === 'home' && (
          <GatewayHero
            onOpenVoice={handleOpenVoice}
            onSelectCategory={handleSelectCategory}
            lang={lang}
          />
        )}

        {/* VIEW 2: Guided Questionnaire */}
        {currentView === 'questionnaire' && selectedCategory && (
          <Questionnaire
            category={selectedCategory}
            currentStepIndex={currentStepIndex}
            answers={answers}
            profile={profile}
            onAnswerChange={handleAnswerChange}
            onNext={handleNext}
            onBack={handleBack}
            onSubmit={handleSubmitQuestionnaire}
            lang={lang}
          />
        )}

        {/* VIEW 3: Finding Schemes Loading */}
        {currentView === 'loading' && (
          <div className="loading-container" role="status">
            <span className="loading-spinner-large" aria-hidden="true" />
            <h3 className="loading-title">
              {getLocaleString(lang, 'findingSchemesLoading')}
            </h3>
          </div>
        )}

        {/* VIEW 4: Results */}
        {currentView === 'results' && (
          <>
            {activeError && (
              <div className="error-card" role="alert">
                <span className="error-icon" aria-hidden="true">⚠️</span>
                <div className="error-body">
                  <h4>{getLocaleString(lang, 'errorTitle')}</h4>
                  <p>{activeError}</p>
                  <div className="error-actions">
                    <button
                      type="button"
                      className="btn-step-continue"
                      onClick={handleSubmitQuestionnaire}
                    >
                      {getLocaleString(lang, 'tryAgain')}
                    </button>
                    <button
                      type="button"
                      className="btn-step-back"
                      onClick={handleReset}
                    >
                      {getLocaleString(lang, 'startOver')}
                    </button>
                  </div>
                </div>
              </div>
            )}

            {!activeError && (
              <ResultsView
                results={results}
                disclaimer={disclaimer}
                profile={profile}
                locationOptions={locationOptions}
                onChangeAnswers={handleChangeAnswers}
                onReset={handleReset}
                onViewDetails={handleViewDetails}
                lang={lang}
              />
            )}
          </>
        )}
      </main>

      {/* Floating Voice Agent (kept mounted so the conversation and session persist across navigation) */}
      <VoiceAssistantView
        lang={lang}
        openSignal={voiceOpenSignal}
        onViewDetails={handleViewDetails}
        onLanguageChange={setLang}
      />

      {/* Scheme Details Modal */}
      {detailModal.isOpen && (
        <SchemeDetailModal
          schemeId={detailModal.schemeId}
          schemeName={detailModal.schemeName}
          schemeData={detailModal.schemeData}
          profile={profile}
          locationOptions={locationOptions}
          onClose={handleCloseDetails}
          lang={lang}
        />
      )}
    </div>
  );
}

export default App;
