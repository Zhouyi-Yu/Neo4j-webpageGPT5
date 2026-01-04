import React, { useState, useRef, useEffect } from 'react';
import { Send, StopCircle, RefreshCw, Layers, ChevronRight } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import Message from './components/Chat/Message';
import DebugPanel from './components/Debug/DebugPanel';
import DebugLogModal from './components/Debug/DebugLogModal';
import Logo from './components/UI/Logo';
import { cn } from './lib/utils';

export default function App() {
    const [messages, setMessages] = useState([
        {
            role: 'assistant',
            content: 'Hello! I can help you find research information at the University of Alberta. Try asking about specific researchers (e.g., "Marek Reformat"), topics ("smart grids"), or departments.'
        }
    ]);
    const [input, setInput] = useState('');
    const [isThinking, setIsThinking] = useState(false);
    const [status, setStatus] = useState('');
    const [elapsedTime, setElapsedTime] = useState(0);
    const [debugData, setDebugData] = useState({ intent: null, cypher: null, dbRows: null, semanticHits: null, telemetry: null });
    const [isDebugOpen, setIsDebugOpen] = useState(false);
    const [isLogsOpen, setIsLogsOpen] = useState(false);
    const [candidates, setCandidates] = useState([]);
    const [pendingQuestion, setPendingQuestion] = useState('');

    const chatEndRef = useRef(null);
    const abortControllerRef = useRef(null);

    const scrollToBottom = () => {
        chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
    };


    useEffect(() => {
        let interval;
        if (isThinking) {
            const startTime = performance.now();
            interval = setInterval(() => {
                setElapsedTime((performance.now() - startTime) / 1000);
            }, 100);
        } else {
            setElapsedTime(0);
        }
        return () => clearInterval(interval);
    }, [isThinking]);

    useEffect(() => {
        scrollToBottom();
    }, [messages, isThinking]);

    // Mirror logDebugEntry from index.html
    const logDebugEntry = async (question, data) => {
        const entry = {
            timestamp: new Date().toISOString(),
            question: question,
            answer: data.answer || '',
            intent: data.intent || {},
            cypher: data.cypher || '',
            dbRows: data.dbRows || [],
            semanticHits: data.semanticHits || [],
            telemetry: data.telemetry || {}
        };

        try {
            await fetch('/api/log-debug', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(entry)
            });
        } catch (err) {
            console.error('Failed to log debug entry:', err);
        }
    };

    const handleSubmit = async (e, selectedUserId = null) => {
        if (e) e.preventDefault();
        const question = input.trim();
        if (!question && !selectedUserId) return;

        // Reset state for new question
        setIsThinking(true);
        setStatus('Processing...');
        setCandidates([]);

        // Add user message to UI
        if (!selectedUserId) {
            setMessages(prev => [...prev, { role: 'user', content: question }]);
            setInput('');
        }

        const startTime = performance.now();
        abortControllerRef.current = new AbortController();

        try {
            const currentQuestion = selectedUserId ? pendingQuestion : question;
            const response = await fetch('/api/query', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    question: currentQuestion,
                    selected_user_id: selectedUserId
                }),
                signal: abortControllerRef.current.signal
            });

            let data;
            try {
                data = await response.json();
            } catch (parseErr) {
                // Not JSON or empty body
            }

            if (data) {
                setDebugData({
                    intent: data.intent,
                    cypher: data.cypher,
                    dbRows: data.dbRows,
                    semanticHits: data.semanticHits,
                    telemetry: data.telemetry
                });

                // Log telemetry even for partial results/errors if they came from the pipeline
                logDebugEntry(selectedUserId ? "Author Selection" : question, data);
            }

            if (!response.ok) {
                const errorMsg = data?.answer || data?.error || `Server Error: ${response.status}`;
                throw new Error(errorMsg);
            }

            const duration = ((performance.now() - startTime) / 1000).toFixed(1);

            if (data.candidates && data.candidates.length > 0) {
                setCandidates(data.candidates);
                setPendingQuestion(currentQuestion); // Preserve the original question
                setMessages(prev => [...prev, {
                    role: 'assistant',
                    content: data.answer || "I found multiple researchers. Please select one:",
                    isCandidateList: true
                }]);
                setStatus(`Waiting for selection... (${duration}s)`);
            } else {
                setMessages(prev => [...prev, { role: 'assistant', content: data.answer }]);
                setStatus(`Done in ${duration}s.`);
                setPendingQuestion(''); // Clear on success
            }

        } catch (err) {
            if (err.name === 'AbortError') {
                setMessages(prev => [...prev, { role: 'assistant', content: '_Thinking stopped._' }]);
                setStatus('Stopped.');
            } else {
                // Specifically detect connection failures
                const isOffline = err instanceof TypeError || err.message.includes('fetch');
                const displayError = isOffline
                    ? 'Error: Connection failed. The backend server is offline. Please run ./start.sh'
                    : (err.message.includes('Error:') ? err.message : `Error: ${err.message}`);

                setMessages(prev => [...prev, { role: 'assistant', content: displayError }]);
                setStatus('Error occurred.');
            }
        } finally {
            setIsThinking(false);
            abortControllerRef.current = null;
        }
    };

    const handleStop = () => {
        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
        }
    };

    const selectCandidate = (candidate) => {
        handleSubmit(null, candidate.userId);
    };

    return (
        <div className="flex h-screen bg-[#0f172a] overflow-hidden">
            {/* Sidebar Overlay Toggle */}
            <button
                onClick={() => setIsDebugOpen(!isDebugOpen)}
                className="fixed top-6 right-6 z-[1100] flex items-center gap-2 px-4 py-2 rounded-full bg-slate-800 border border-slate-700 text-slate-300 hover:text-white transition-all shadow-lg text-sm"
            >
                <Layers size={16} />
                {isDebugOpen ? 'Hide Debug' : 'Show Debug'}
            </button>

            <main className="flex-1 flex flex-col items-center p-6 w-full overflow-hidden">
                <div className="w-full max-w-4xl flex flex-col h-full bg-[#0b1224] rounded-3xl border border-slate-800/50 shadow-2xl overflow-hidden relative z-0">
                    {/* Header */}
                    <header className="p-6 bg-slate-900/50 border-b border-slate-800 flex items-center justify-between">
                        <div>
                            <h1 className="text-xl font-bold text-white flex items-center gap-3">
                                <span className="w-2 h-6 bg-blue-500 rounded-full" />
                                UAlberta Research Assistant
                            </h1>
                            <p className="text-xs text-slate-500 mt-1">Neo4j Graph Discovery + Speculative Synthesis</p>
                        </div>
                        <div className="flex items-center gap-4 text-xs font-medium text-slate-400">
                            {isThinking && (
                                <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-blue-500/10 border border-blue-500/20 text-blue-400 font-mono animate-pulse">
                                    <RefreshCw size={12} className="animate-spin" />
                                    {elapsedTime.toFixed(1)}s
                                </span>
                            )}
                            <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
                                {!isThinking && <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />}
                                API Connected
                            </span>
                        </div>
                    </header>

                    {/* Chat Container */}
                    <div className="flex-1 overflow-y-auto p-6 space-y-6 flex flex-col">
                        <AnimatePresence initial={false}>
                            {messages.map((msg, idx) => (
                                <div key={idx} className="flex flex-col space-y-4">
                                    <Message role={msg.role} content={msg.content}>
                                        {msg.isCandidateList && candidates.length > 0 && (
                                            <div className="mt-4 grid grid-cols-1 gap-2 max-h-60 overflow-y-auto pr-2">
                                                {candidates.map((c, cIdx) => (
                                                    <button
                                                        key={cIdx}
                                                        onClick={() => selectCandidate(c)}
                                                        className="flex items-center justify-between p-3 rounded-xl bg-slate-900 border border-slate-800 hover:border-blue-500/50 hover:bg-slate-800 transition-all text-left"
                                                    >
                                                        <div>
                                                            <div className="text-sm font-bold text-slate-200">{c.name || c.normalized_name}</div>
                                                            <div className="text-[10px] text-slate-500 mt-0.5 line-clamp-1">
                                                                {Array.isArray(c.departments) ? c.departments.join(', ') : 'Researcher'}
                                                            </div>
                                                        </div>
                                                        <ChevronRight size={14} className="text-slate-600" />
                                                    </button>
                                                ))}
                                            </div>
                                        )}
                                    </Message>
                                </div>
                            ))}
                        </AnimatePresence>

                        {isThinking && (
                            <motion.div
                                initial={{ opacity: 0, y: 10 }}
                                animate={{ opacity: 1, y: 0 }}
                                className="flex items-center gap-3 text-slate-400 p-2"
                            >
                                <div className="flex gap-1">
                                    {[0, 1, 2].map(i => (
                                        <motion.span
                                            key={i}
                                            animate={{ opacity: [0.4, 1, 0.4] }}
                                            transition={{ repeat: Infinity, duration: 1.5, delay: i * 0.2 }}
                                            className="w-1.5 h-1.5 bg-blue-500 rounded-full"
                                        />
                                    ))}
                                </div>
                                <span className="text-sm font-medium italic">Thinking...</span>
                            </motion.div>
                        )}
                        <div ref={chatEndRef} />
                    </div>

                    {/* Input Area */}
                    <div className="p-6 bg-slate-900/80 border-top border-slate-800 backdrop-blur-md">
                        <form onSubmit={handleSubmit} className="relative">
                            <textarea
                                value={input}
                                onChange={(e) => setInput(e.target.value)}
                                onKeyDown={(e) => {
                                    if (e.key === 'Enter' && !e.shiftKey) {
                                        e.preventDefault();
                                        handleSubmit();
                                    }
                                }}
                                placeholder="Ask about UAlberta research... (e.g. reinforcement learning experts)"
                                className="w-full bg-slate-950 text-slate-100 rounded-2xl border border-slate-800 p-4 pr-32 focus:outline-none focus:border-blue-500 transition-all min-h-[80px] max-h-[200px] resize-none"
                            />
                            <div className="absolute right-4 bottom-4 flex items-center gap-2">
                                <span className="text-[10px] text-slate-600 font-mono hidden sm:inline mr-2">{status}</span>
                                {isThinking ? (
                                    <button
                                        type="button"
                                        onClick={handleStop}
                                        className="p-3 bg-red-500 rounded-xl text-white hover:bg-red-400 transition-all shadow-lg shadow-red-500/20"
                                    >
                                        <StopCircle size={20} />
                                    </button>
                                ) : (
                                    <button
                                        type="submit"
                                        disabled={!input.trim()}
                                        className="p-3 bg-blue-600 rounded-xl text-white hover:bg-blue-500 disabled:opacity-50 disabled:bg-slate-800 transition-all shadow-lg shadow-blue-500/20"
                                    >
                                        <Send size={20} />
                                    </button>
                                )}
                            </div>
                        </form>
                    </div>
                </div>
            </main>

            <Logo />

            <DebugPanel
                data={debugData}
                isThinking={isThinking}
                isOpen={isDebugOpen}
                onOpenLogs={() => setIsLogsOpen(true)}
            />

            <DebugLogModal
                isOpen={isLogsOpen}
                onClose={() => setIsLogsOpen(false)}
            />
        </div>
    );
}
