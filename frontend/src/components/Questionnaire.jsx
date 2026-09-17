import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { getLocaleString } from '../constants/strings';
import { getActiveSteps } from '../constants/questionnaires';
import { fetchLocationDistricts, fetchLocationTalukas } from '../api';

export function Questionnaire({
  category,
  currentStepIndex,
  answers,
  profile,
  onAnswerChange,
  onNext,
  onBack,
  onSubmit,
  lang,
}) {
  const activeSteps = useMemo(() => getActiveSteps(category, profile), [category, profile]);
  const currentStep = activeSteps[currentStepIndex] || activeSteps[0] || category.steps[0];
  const totalSteps = activeSteps.length;
  const isLastStep = currentStepIndex >= totalSteps - 1;

  // Local validation error message
  const [errorMessage, setErrorMessage] = useState(null);

  // Dynamic location options state
  const [dynamicOptions, setDynamicOptions] = useState([]);
  const [isLoadingDynamic, setIsLoadingDynamic] = useState(false);
  const [dynamicError, setDynamicError] = useState(null);
  const dynamicCacheRef = useRef({});

  // Clear error whenever step changes
  useEffect(() => {
    setErrorMessage(null);
  }, [currentStepIndex]);

  const loadDynamicLocationOptions = useCallback(async () => {
    if (!currentStep.isDynamic) return;

    if (currentStep.dynamicType === 'district') {
      const state = profile?.state;
      if (!state) {
        setDynamicOptions([]);
        return;
      }
      const cacheKey = `districts:${state.toLowerCase()}`;
      if (dynamicCacheRef.current[cacheKey]) {
        setDynamicOptions(dynamicCacheRef.current[cacheKey]);
        setDynamicError(null);
        return;
      }

      setIsLoadingDynamic(true);
      setDynamicError(null);
      try {
        const data = await fetchLocationDistricts(state);
        if (data && data.available && Array.isArray(data.districts) && data.districts.length > 0) {
          const formatted = [
            ...data.districts.map((d) => ({
              value: d.name.toLowerCase(),
              label: d.name,
            })),
            { value: 'other', labelKey: 'otherDistrictOption' },
          ];
          dynamicCacheRef.current[cacheKey] = formatted;
          setDynamicOptions(formatted);
          setDynamicError(null);
        } else {
          setDynamicOptions([{ value: 'other', labelKey: 'otherDistrictOption' }]);
          setDynamicError(getLocaleString(lang, 'errorLoadingDistricts'));
        }
      } catch (err) {
        setDynamicOptions([{ value: 'other', labelKey: 'otherDistrictOption' }]);
        setDynamicError(getLocaleString(lang, 'errorLoadingDistricts'));
      } finally {
        setIsLoadingDynamic(false);
      }
    } else if (currentStep.dynamicType === 'taluka') {
      const state = profile?.state;
      const district = profile?.district;
      if (!district || district === 'other') {
        setDynamicOptions([]);
        return;
      }
      const cacheKey = `talukas:${(state || '').toLowerCase()}:${district.toLowerCase()}`;
      if (dynamicCacheRef.current[cacheKey]) {
        setDynamicOptions(dynamicCacheRef.current[cacheKey]);
        setDynamicError(null);
        return;
      }

      setIsLoadingDynamic(true);
      setDynamicError(null);
      try {
        const data = await fetchLocationTalukas(state, district);
        if (data && data.available && Array.isArray(data.talukas) && data.talukas.length > 0) {
          const formatted = [
            ...data.talukas.map((t) => ({
              value: t.name.toLowerCase(),
              label: t.name,
            })),
            { value: 'other', labelKey: 'otherTalukaOption' },
          ];
          dynamicCacheRef.current[cacheKey] = formatted;
          setDynamicOptions(formatted);
          setDynamicError(null);
        } else {
          setDynamicOptions([{ value: 'other', labelKey: 'otherTalukaOption' }]);
          setDynamicError(getLocaleString(lang, 'errorLoadingTalukas'));
        }
      } catch (err) {
        setDynamicOptions([{ value: 'other', labelKey: 'otherTalukaOption' }]);
        setDynamicError(getLocaleString(lang, 'errorLoadingTalukas'));
      } finally {
        setIsLoadingDynamic(false);
      }
    }
  }, [currentStep, profile?.state, profile?.district, lang]);

  useEffect(() => {
    if (currentStep.isDynamic) {
      loadDynamicLocationOptions();
    } else {
      setDynamicOptions([]);
      setDynamicError(null);
      setIsLoadingDynamic(false);
    }
  }, [currentStepIndex, currentStep.id, profile?.state, profile?.district, loadDynamicLocationOptions]);

  const currentValue = answers[currentStep.id];

  const handleContinue = (e) => {
    e?.preventDefault();

    // Validation rules
    if (currentStep.type === 'number') {
      if (currentValue === undefined || currentValue === null || currentValue === '') {
        setErrorMessage(getLocaleString(lang, currentStep.errorKey || 'ageError'));
        return;
      }
      const num = Number(currentValue);
      if (isNaN(num) || num < currentStep.min || num > currentStep.max) {
        setErrorMessage(getLocaleString(lang, currentStep.errorKey || 'ageError'));
        return;
      }
    } else if (currentStep.type === 'select') {
      if (!currentValue && !currentStep.optional) {
        setErrorMessage(getLocaleString(lang, currentStep.errorKey || 'stateError'));
        return;
      }
    } else if (currentStep.type === 'single_choice') {
      if (currentValue === undefined && !currentStep.optional) {
        setErrorMessage(getLocaleString(lang, 'selectOptionPrompt'));
        return;
      }
    }

    setErrorMessage(null);

    if (isLastStep) {
      onSubmit();
    } else {
      onNext();
    }
  };

  const selectOptions = currentStep.isDynamic
    ? dynamicOptions
    : (currentStep.optionsByDistrict
      ? (currentStep.optionsByDistrict[profile?.district] || [])
      : (currentStep.options || []));

  const progressPercent = Math.round(((currentStepIndex + 1) / totalSteps) * 100);

  return (
    <div className="questionnaire-card" role="region" aria-label={getLocaleString(lang, category.titleKey)}>
      {/* Category header & progress */}
      <div className="questionnaire-header">
        <div className="category-meta">
          <span className="category-meta-icon" aria-hidden="true">{category.icon}</span>
          <div>
            <h2 className="category-meta-title">
              {getLocaleString(lang, category.titleKey)}
            </h2>
            <p className="category-meta-subtitle">
              {getLocaleString(lang, 'questionnaireSubtitle')}
            </p>
          </div>
        </div>

        {/* Accessible Progress Indicator */}
        <div
          className="progress-section"
          aria-label={getLocaleString(lang, 'stepIndicator', {
            current: currentStepIndex + 1,
            total: totalSteps,
          })}
        >
          <div className="progress-text-row">
            <span className="progress-step-text">
              {getLocaleString(lang, 'stepIndicator', {
                current: currentStepIndex + 1,
                total: totalSteps,
              })}
            </span>
            <span className="progress-pct-text">{progressPercent}%</span>
          </div>
          <div
            className="progress-bar-track"
            role="progressbar"
            aria-valuenow={progressPercent}
            aria-valuemin="0"
            aria-valuemax="100"
          >
            <div
              className="progress-bar-fill"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
        </div>
      </div>

      {/* Question Body */}
      <form className="questionnaire-body" onSubmit={handleContinue}>
        <fieldset className="question-fieldset">
          <legend className="question-legend">
            {getLocaleString(lang, currentStep.questionKey)}
          </legend>

          {/* Helper / Pilot transparency notice if present */}
          {currentStep.helperNoteKey && (
            <div className="step-pilot-note" role="note">
              <span className="pilot-note-icon" aria-hidden="true">ℹ️</span>
              <span className="pilot-note-text">
                {getLocaleString(lang, currentStep.helperNoteKey)}
              </span>
            </div>
          )}

          {/* Type: Number Input (Age) */}
          {currentStep.type === 'number' && (
            <div className="input-group">
              <input
                id={`input-${currentStep.id}`}
                type="number"
                className="input-number"
                min={currentStep.min}
                max={currentStep.max}
                value={currentValue !== undefined ? currentValue : ''}
                placeholder={getLocaleString(lang, currentStep.placeholderKey)}
                onChange={(e) => {
                  const val = e.target.value === '' ? '' : parseInt(e.target.value, 10);
                  onAnswerChange(currentStep.id, val, { [currentStep.field]: val === '' ? null : val });
                  if (errorMessage) setErrorMessage(null);
                }}
                autoFocus
                aria-required="true"
                aria-describedby={errorMessage ? `err-${currentStep.id}` : undefined}
              />
            </div>
          )}

          {/* Type: Select Input (State, District, Taluka) */}
          {currentStep.type === 'select' && (
            <div className="input-group">
              <select
                id={`select-${currentStep.id}`}
                className="input-select"
                value={currentValue || ''}
                disabled={isLoadingDynamic}
                onChange={(e) => {
                  const val = e.target.value;
                  onAnswerChange(currentStep.id, val, { [currentStep.field]: val || null });
                  if (errorMessage) setErrorMessage(null);
                }}
                autoFocus
                aria-required={!currentStep.optional}
                aria-describedby={errorMessage ? `err-${currentStep.id}` : undefined}
              >
                <option value="">
                  {isLoadingDynamic
                    ? getLocaleString(lang, currentStep.id === 'district' ? 'loadingDistricts' : 'loadingTalukas')
                    : getLocaleString(lang, currentStep.placeholderKey)}
                </option>
                {selectOptions.map((opt) => {
                  const displayLabel = opt.labels
                    ? (opt.labels[lang] || opt.labels.en)
                    : (opt.labelKey ? getLocaleString(lang, opt.labelKey) : (opt.label || opt.value));
                  return (
                    <option key={opt.value} value={opt.value}>
                      {displayLabel}
                    </option>
                  );
                })}
              </select>

              {/* Dynamic location loading indicator */}
              {isLoadingDynamic && (
                <div className="dynamic-location-status" role="status">
                  <span>⏳ {getLocaleString(lang, currentStep.id === 'district' ? 'loadingDistricts' : 'loadingTalukas')}</span>
                </div>
              )}

              {/* Dynamic location error with retry button */}
              {!isLoadingDynamic && dynamicError && (
                <div className="dynamic-location-status dynamic-location-error" role="alert">
                  <span>⚠️ {dynamicError}</span>
                  <button
                    type="button"
                    className="btn-location-retry"
                    onClick={loadDynamicLocationOptions}
                  >
                    🔄 {getLocaleString(lang, 'retryLocationButton')}
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Type: Single Choice Cards */}
          {currentStep.type === 'single_choice' && (
            <div className="choice-grid" role="radiogroup" aria-label={getLocaleString(lang, currentStep.questionKey)}>
              {currentStep.options.map((opt, idx) => {
                const isSelected = currentValue === opt.value;
                const optLabel = opt.labelKey ? getLocaleString(lang, opt.labelKey) : (opt.labels ? (opt.labels[lang] || opt.labels.en) : opt.label);
                return (
                  <button
                    key={idx}
                    type="button"
                    role="radio"
                    aria-checked={isSelected}
                    className={`choice-card ${isSelected ? 'selected' : ''}`}
                    onClick={() => {
                      onAnswerChange(currentStep.id, opt.value, opt.profilePatch);
                      if (errorMessage) setErrorMessage(null);
                    }}
                  >
                    <span className="choice-indicator" aria-hidden="true">
                      {isSelected ? '●' : '○'}
                    </span>
                    <span className="choice-text">{optLabel}</span>
                  </button>
                );
              })}
            </div>
          )}

          {/* Error Message if validation fails */}
          {errorMessage && (
            <div id={`err-${currentStep.id}`} className="validation-error" role="alert">
              <span aria-hidden="true">⚠️</span> {errorMessage}
            </div>
          )}
        </fieldset>

        {/* Footer Navigation Buttons */}
        <div className="questionnaire-footer">
          <button
            type="button"
            className="btn-step-back"
            onClick={onBack}
            aria-label={getLocaleString(lang, 'backButton')}
          >
            {getLocaleString(lang, 'backButton')}
          </button>

          <button
            type="submit"
            className="btn-step-continue"
            aria-label={isLastStep ? getLocaleString(lang, 'submitButton') : getLocaleString(lang, 'continueButton')}
          >
            {isLastStep
              ? getLocaleString(lang, 'submitButton')
              : getLocaleString(lang, 'continueButton')}
          </button>
        </div>
      </form>
    </div>
  );
}

export default Questionnaire;
