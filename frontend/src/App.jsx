import React, { useState, useRef, useEffect } from 'react';
import Header from './components/Header';
import WelcomeScreen from './components/WelcomeScreen';
import ChatMessage from './components/ChatMessage';
import ChatInput from './components/ChatInput';
import LoadingMessage from './components/LoadingMessage';
import { sendChatMessage } from './api';
import { t } from './constants/strings';

function App() {
  const [messages, setMessages] = useState([]);
  const [currentProfile, setCurrentProfile] = useState({});
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  const handleReset = () => {
    setMessages([]);
    setCurrentProfile({});
    setError(null);
    setIsLoading(false);
  };

  const handleSendMessage = async (userText) => {
    if (!userText.trim() || isLoading) return;

    setError(null);
    const userMsg = {
      id: `user-${Date.now()}`,
      sender: 'user',
      text: userText.trim(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);

    try {
      // Send current conversation profile state with message
      const response = await sendChatMessage(userText.trim(), currentProfile);

      // Maintain conversational profile state
      if (response.profile) {
        setCurrentProfile(response.profile);
      }

      const assistantMsg = {
        id: `assistant-${Date.now()}`,
        sender: 'assistant',
        text: response.message || response.question || '',
        schemes: response.schemes || [],
        disclaimer: response.disclaimer || null,
        needsMoreInfo: response.needs_more_information || false,
      };

      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      let friendlyError = t('errorGeneric');
      if (err.response) {
        const status = err.response.status;
        if (status === 400) {
          friendlyError = t('errorBadRequest');
        } else if (status === 502) {
          friendlyError = t('errorBadGateway');
        } else if (status === 503) {
          friendlyError = t('errorServiceUnavailable');
        } else if (err.response.data?.detail) {
          friendlyError = String(err.response.data.detail);
        }
      } else if (err.request) {
        friendlyError = t('errorNetwork');
      }

      setError(friendlyError);
    } finally {
      setIsLoading(false);
    }
  };

  const hasConversation = messages.length > 0;

  return (
    <div className="app-layout">
      <Header onReset={handleReset} hasConversation={hasConversation} />

      <main className="chat-main" role="main">
        {!hasConversation ? (
          <WelcomeScreen onSelectSuggestion={handleSendMessage} />
        ) : (
          <div className="conversation-container" aria-live="polite">
            {messages.map((msg) => (
              <ChatMessage key={msg.id} message={msg} />
            ))}
            {isLoading && <LoadingMessage />}
            <div ref={messagesEndRef} />
          </div>
        )}

        {error && (
          <div className="error-banner" role="alert">
            <span className="error-icon" aria-hidden="true">⚠️</span>
            <div className="error-content">
              <p className="error-text">{error}</p>
            </div>
            <button
              type="button"
              className="btn-dismiss-error"
              onClick={() => setError(null)}
              aria-label="Dismiss error"
            >
              ✕
            </button>
          </div>
        )}
      </main>

      <footer className="chat-footer">
        <ChatInput onSendMessage={handleSendMessage} isLoading={isLoading} />
      </footer>
    </div>
  );
}

export default App;
