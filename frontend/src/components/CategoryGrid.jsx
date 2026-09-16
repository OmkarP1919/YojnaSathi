import React from 'react';
import { CATEGORIES } from '../constants/questionnaires';
import { getLocaleString } from '../constants/strings';

export function CategoryGrid({ onSelectCategory, lang }) {
  return (
    <section className="category-section" aria-labelledby="category-heading">
      <div className="hero-banner">
        <span className="hero-badge" aria-hidden="true">
          🇮🇳 {getLocaleString(lang, 'heroBadge')}
        </span>
        <h2 className="hero-title">{getLocaleString(lang, 'heroTitle')}</h2>
        <p className="hero-subtitle">{getLocaleString(lang, 'heroSubtitle')}</p>
      </div>

      <div className="section-prompt-box">
        <h3 id="category-heading" className="section-heading">
          {getLocaleString(lang, 'categoryHeading')}
        </h3>
        <p className="section-subheading">
          {getLocaleString(lang, 'categorySubtitle')}
        </p>
      </div>

      <div className="category-grid" role="list">
        {CATEGORIES.map((cat) => (
          <button
            key={cat.id}
            type="button"
            className="category-card"
            onClick={() => onSelectCategory(cat)}
            role="listitem"
            aria-label={`${getLocaleString(lang, cat.titleKey)}: ${getLocaleString(lang, cat.descKey)}`}
          >
            <div className="category-card-icon" aria-hidden="true">
              {cat.icon}
            </div>
            <div className="category-card-info">
              <h4 className="category-card-title">
                {getLocaleString(lang, cat.titleKey)}
              </h4>
              <p className="category-card-desc">
                {getLocaleString(lang, cat.descKey)}
              </p>
            </div>
            <span className="category-card-arrow" aria-hidden="true">→</span>
          </button>
        ))}
      </div>
    </section>
  );
}

export default CategoryGrid;
