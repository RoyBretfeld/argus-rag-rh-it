import { useState, useRef, useEffect } from 'react';

type Message = {
  role: 'user' | 'assistant';
  content: string;
  sources?: Record<string, unknown>[];
  verification?: SourceVerification;
};

type SourceConflict = {
  topic: string;
  source_a: string;
  value_a: string;
  source_b: string;
  value_b: string;
  severity: string;
};

type SourceVerification = {
  confidence: number;
  confidence_label: 'hoch' | 'mittel' | 'niedrig';
  source_quality: 'hoch' | 'mittel' | 'niedrig';
  verdict: 'sicher' | 'teilweise_unsicher' | 'widerspruch_gefunden' | 'menschliche_pruefung_empfohlen';
  needs_human_review: boolean;
  conflicts: SourceConflict[];
  source_counts: {
    total: number;
    internal: number;
    web: number;
  };
  evidence_notes: string[];
};

type ChatResponse = {
  response?: {
    antwort: string;
    rag_quellen?: Record<string, unknown>[];
    web_quellen?: Record<string, unknown>[];
    verification?: SourceVerification;
  };
  error?: string;
};

const getErrorMessage = (error: unknown) => (
  error instanceof Error ? error.message : 'Unbekannter Fehler'
);

export default function ChatPanel() {
  const [mode, setMode] = useState('wissensbasis');
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([
    { role: 'assistant', content: 'ARGUS Query Console bereit. Lade Knowledge Payloads oder stelle eine Prüfanfrage.' }
  ]);
  const [isLoading, setIsLoading] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim()) return;
    
    const userMsg = input;
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: userMsg }]);
    setIsLoading(true);

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          frage: userMsg,
          modus: mode,
          vertraulich: false
        })
      });
      const data = await response.json() as ChatResponse;
      
      const chatResponse = data.response;
      if (response.ok && chatResponse) {
        setMessages(prev => [...prev, { 
          role: 'assistant', 
          content: chatResponse.antwort,
          sources: [...(chatResponse.rag_quellen || []), ...(chatResponse.web_quellen || [])],
          verification: chatResponse.verification
        }]);
      } else {
        setMessages(prev => [...prev, { role: 'assistant', content: `Fehler: ${data.error || 'Unbekannt'}` }]);
      }
    } catch (error: unknown) {
      setMessages(prev => [...prev, { role: 'assistant', content: `Verbindungsfehler: ${getErrorMessage(error)}` }]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="chat-area">
      <header className="command-header">
        <div className="command-title">
          <span>[ARGUS] COMMAND CENTER v0.4</span>
          <strong>rh-it Dresden</strong>
        </div>
        <div className="command-status">
          <span>SYSTEM <strong>SECURE</strong></span>
          <span>TRUST CORE <strong>ACTIVE</strong></span>
        </div>
      </header>

      <div className="mode-strip">
        <div className="segmented-control">
          <button className={`segment-btn ${mode === 'wissensbasis' ? 'active' : ''}`} onClick={() => setMode('wissensbasis')}>
            Wissensbasis
          </button>
          <button className={`segment-btn ${mode === 'internet' ? 'active' : ''}`} onClick={() => setMode('internet')}>
            Internet
          </button>
          <button className={`segment-btn ${mode === 'beides' ? 'active' : ''}`} onClick={() => setMode('beides')}>
            Hybrid
          </button>
        </div>
        <div className="system-chip-row">
          <span>RAG ONLINE</span>
          <span>CHROMA CONNECTED</span>
          <span>SOURCE VALIDATION</span>
        </div>
      </div>

      <div className="chat-history">
        {messages.length === 1 && !isLoading && (
          <section className="console-overview" aria-label="ARGUS Systemübersicht">
            <div className="overview-hero">
              <div>
                <div className="overview-kicker">OPERATIONAL SURFACE</div>
                <h2>Knowledge Core bereit für Ingestion und Prüfung.</h2>
                <p>ARGUS verbindet lokale Dokumentensuche, hybride Recherche und Source Validation zu einer prüfbaren Antwortkette.</p>
              </div>
              <div className="overview-score">
                <span>TRUST CORE</span>
                <strong>ACTIVE</strong>
              </div>
            </div>

            <div className="overview-grid">
              <article className="overview-card">
                <span>01</span>
                <h3>Knowledge Intake</h3>
                <p>Dokumente, Bilder und technische Daten werden in Chunks zerlegt und lokal indexiert.</p>
                <div className="card-meter"><i style={{ width: '82%' }}></i></div>
              </article>
              <article className="overview-card">
                <span>02</span>
                <h3>Vector Retrieval</h3>
                <p>Hybrid Search kombiniert Vektorraum, BM25 und Re-Ranking für präzisere Treffer.</p>
                <div className="card-meter"><i style={{ width: '76%' }}></i></div>
              </article>
              <article className="overview-card">
                <span>03</span>
                <h3>Source Validation</h3>
                <p>Confidence, Quellenqualität und Widersprüche werden direkt neben Antworten sichtbar.</p>
                <div className="card-meter hot"><i style={{ width: '94%' }}></i></div>
              </article>
              <article className="overview-card">
                <span>04</span>
                <h3>Local Sovereignty</h3>
                <p>Vertrauliche Daten bleiben lokal. Websuche ist ein zuschaltbarer Modus, nicht Pflicht.</p>
                <div className="card-meter"><i style={{ width: '88%' }}></i></div>
              </article>
            </div>

            <div className="protocol-panel">
              <div className="protocol-head">
                <span>QUERY PROTOCOL</span>
                <strong>READY</strong>
              </div>
              <div className="protocol-lines">
                <p><b>WISSENSBASIS</b> Interne Dokumente mit Quellenpflicht.</p>
                <p><b>INTERNET</b> Websuche für öffentliche Recherche.</p>
                <p><b>HYBRID</b> Synthese aus lokalem Wissen und aktueller Außenquelle.</p>
              </div>
            </div>
          </section>
        )}

        {messages.map((msg, idx) => (
          <div key={idx} className={`message ${msg.role}`}>
            <div className="message-bubble">
              {msg.content}
            </div>
            {msg.sources && msg.sources.length > 0 && (
              <div className="source-count">
                Quellen: {msg.sources.length}
              </div>
            )}
            {msg.verification && (
              <div className={`verification-card ${msg.verification.verdict}`}>
                <div className="verification-row">
                  <span className="verification-label">{formatVerdict(msg.verification.verdict)}</span>
                  <span>{Math.round(msg.verification.confidence * 100)}% Sicherheit</span>
                </div>
                <div className="verification-meta">
                  Intern {msg.verification.source_counts.internal} · Web {msg.verification.source_counts.web} · Qualität {msg.verification.source_quality}
                </div>
                {msg.verification.conflicts.length > 0 && (
                  <div className="verification-conflict">
                    Widerspruch: {msg.verification.conflicts[0].value_a} vs. {msg.verification.conflicts[0].value_b}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
        {isLoading && (
          <div className="message assistant">
            <div className="message-bubble" style={{ opacity: 0.7 }}>
              Denkt nach...
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <div className="chat-input-wrapper">
        <div className="query-prefix">SMART ROUTER ({mode.toUpperCase()})</div>
        <input 
          type="text" 
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSend()}
          placeholder="ARGUS Query eingeben..." 
        />
      </div>
    </div>
  );
}

function formatVerdict(verdict: SourceVerification['verdict']) {
  switch (verdict) {
    case 'sicher':
      return 'Sicher';
    case 'teilweise_unsicher':
      return 'Teilweise unsicher';
    case 'widerspruch_gefunden':
      return 'Widerspruch gefunden';
    case 'menschliche_pruefung_empfohlen':
      return 'Prüfung empfohlen';
  }
}
