import React, { useState, useEffect } from 'react';
import { X, Clock, FileText, Database, Code, Zap } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { cn } from '../../lib/utils';

const DebugLogModal = ({ isOpen, onClose }) => {
    const [entries, setEntries] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    useEffect(() => {
        if (isOpen) {
            loadLogs();
        }
    }, [isOpen]);

    const loadLogs = async () => {
        setLoading(true);
        setError(null);
        try {
            const res = await fetch('/api/debug-log');

            if (!res.ok) {
                const text = await res.text(); // Read text for error message
                throw new Error(text || `Error ${res.status}`);
            }

            const text = await res.text(); // Read text for successful response
            const logs = text.trim().split('\n').filter(Boolean).map(line => {
                try {
                    return JSON.parse(line);
                } catch (e) {
                    console.error("Error parsing log line:", line);
                    return null;
                }
            }).filter(Boolean).reverse();

            setEntries(logs);
        } catch (err) {
            console.error('Failed to load logs:', err);
            // Specifically handle connection failures (TypeError: Failed to fetch)
            if (err instanceof TypeError || err.message.includes('fetch')) {
                setError('Connection Failed: Backend server is offline. Please run ./start.sh');
            } else {
                setError(err.message || 'Failed to load debug log');
            }
        } finally {
            setLoading(false);
        }
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-[2000] flex items-center justify-center p-4">
            <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                onClick={onClose}
                className="absolute inset-0 bg-black/80 backdrop-blur-sm"
            />

            <motion.div
                initial={{ opacity: 0, scale: 0.9, y: 20 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.9, y: 20 }}
                className="relative bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-5xl max-h-[85vh] flex flex-col shadow-2xl overflow-hidden"
            >
                <div className="p-6 border-b border-slate-800 flex items-center justify-between">
                    <div>
                        <h2 className="text-xl font-bold text-white">System Debug Log</h2>
                        <p className="text-xs text-slate-500 mt-1">Telemetry for Neo4j + GPT-5 Pipeline executions</p>
                    </div>
                    <button
                        onClick={onClose}
                        className="p-2 hover:bg-slate-800 rounded-full transition-colors text-slate-400 hover:text-white"
                    >
                        <X size={24} />
                    </button>
                </div>

                <div className="flex-1 overflow-y-auto p-6 space-y-4">
                    {loading ? (
                        <div className="flex flex-col items-center justify-center py-20 gap-4">
                            <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
                            <p className="text-slate-500 text-sm">Retrieving log entries...</p>
                        </div>
                    ) : error ? (
                        <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-xl text-red-400 text-sm">
                            {error}
                        </div>
                    ) : entries.length === 0 ? (
                        <div className="text-center py-20 text-slate-600 italic">No debug entries found.</div>
                    ) : (
                        entries.map((entry, idx) => (
                            <LogEntry key={idx} entry={entry} />
                        ))
                    )}
                </div>
            </motion.div>
        </div>
    );
};

const LogEntry = ({ entry }) => {
    const [expanded, setExpanded] = useState(false);
    const date = new Date(entry.timestamp).toLocaleString();

    return (
        <div className="bg-slate-950/50 border border-slate-800 rounded-xl overflow-hidden transition-all hover:border-slate-700">
            <div
                className="p-4 cursor-pointer flex items-center justify-between"
                onClick={() => setExpanded(!expanded)}
            >
                <div className="flex items-center gap-4 flex-1 min-w-0">
                    <div className="p-2 bg-blue-500/10 rounded-lg text-blue-400">
                        <Clock size={16} />
                    </div>
                    <div className="min-w-0 flex-1">
                        <div className="text-xs font-mono text-slate-500">{date}</div>
                        <div className="text-sm text-slate-300 font-medium truncate mt-0.5">{entry.question}</div>
                    </div>
                </div>
                <div className="flex items-center gap-3">
                    <span className="text-[10px] px-2 py-1 rounded bg-slate-800 text-slate-400 font-bold uppercase tracking-widest">
                        {entry.intent?.intent || 'Unknown Intent'}
                    </span>
                    <div className={`p-1 transition-transform ${expanded ? 'rotate-180' : ''}`}>
                        <X size={14} className="rotate-45" />
                    </div>
                </div>
            </div>

            <AnimatePresence>
                {expanded && (
                    <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        className="border-t border-slate-800"
                    >
                        <div className="p-4 space-y-4 bg-black/20">
                            <LogSection title="Original Question" icon={<Zap size={14} />} content={entry.question} />
                            <LogSection title="AI Synthesis" icon={<FileText size={14} />} content={entry.answer} />
                            <LogSection title="Cypher Query" icon={<Code size={14} />} content={entry.cypher} isCode />
                            <LogSection title="Graph Database Result" icon={<Database size={14} />} content={JSON.stringify(entry.dbRows, null, 2)} isCode />
                            <LogSection title="Semantic Search Insights" icon={<Zap size={14} />} content={JSON.stringify(entry.semanticHits, null, 2)} isCode />
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
};

const LogSection = ({ title, icon, content, isCode }) => (
    <div className="space-y-2">
        <div className="flex items-center gap-2 text-slate-400 text-xs font-bold uppercase tracking-wider">
            {icon}
            <span>{title}</span>
        </div>
        <div className="bg-slate-900/50 border border-slate-800/50 rounded-lg p-3">
            <pre className={cn(
                "text-[11px] leading-relaxed whitespace-pre-wrap break-all font-mono",
                isCode ? "text-purple-300" : "text-slate-300"
            )}>
                {content || '–'}
            </pre>
        </div>
    </div>
);

export default DebugLogModal;
