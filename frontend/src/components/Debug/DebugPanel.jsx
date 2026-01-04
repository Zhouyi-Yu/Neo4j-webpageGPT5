import React from 'react';

const DebugPanel = ({ data, isThinking, isOpen, onOpenLogs }) => {
    return (
        <aside
            className={`fixed top-0 right-0 h-screen bg-[#020617] border-l border-slate-800 p-6 shadow-2xl overflow-y-auto transition-all duration-300 z-[1000] w-[400px] ${isOpen ? 'translate-x-0' : 'translate-x-full'
                }`}
        >
            <div className="mt-12 mb-8">
                <h2 className="text-xl font-bold text-white mb-2">Debug Info</h2>
                <div className="h-1 w-20 bg-blue-500 rounded-full mb-6" />

                {data.telemetry?.timings && (
                    <div className="bg-slate-900/50 border border-slate-800 rounded-2xl p-4 mb-8">
                        <h3 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-4">Latency Breakdown (sec)</h3>
                        <div className="space-y-3">
                            {Object.entries(data.telemetry.timings).map(([step, time]) => (
                                <TimingItem key={step} label={step} value={time} />
                            ))}
                        </div>
                        {data.telemetry.resolution?.resolution_path && (
                            <div className="mt-4 pt-4 border-t border-slate-800/50">
                                <div className="text-[10px] text-slate-500 uppercase font-bold tracking-widest mb-1">Resolution Path</div>
                                <div className="text-sm text-blue-400 font-mono font-bold">
                                    {data.telemetry.resolution.resolution_path}
                                    {data.telemetry.resolution.fuzzy_scores && ` (Scores: ${data.telemetry.resolution.fuzzy_scores.join(', ')})`}
                                </div>
                            </div>
                        )}
                    </div>
                )}
            </div>

            <div className="space-y-6">
                <DebugSection
                    title="Intent (classifier output)"
                    content={data.intent ? JSON.stringify(data.intent, null, 2) : "–"}
                />
                <DebugSection
                    title="Cypher (generated query)"
                    content={data.cypher || "–"}
                    isCode
                />
                <DebugSection
                    title="DB rows (graph query results)"
                    content={data.dbRows ? JSON.stringify(data.dbRows, null, 2) : "[]"}
                />
                <DebugSection
                    title="Semantic hits (vector search)"
                    content={data.semanticHits ? JSON.stringify(data.semanticHits, null, 2) : "[]"}
                />
            </div>

            <div className="mt-10 space-y-3">
                <button
                    onClick={onOpenLogs}
                    className="w-full py-3 px-4 rounded-xl bg-slate-800 border border-slate-700 text-slate-300 hover:text-white hover:bg-slate-700 transition-all text-sm font-semibold flex items-center justify-center gap-2"
                >
                    View Debug Log
                </button>
                <button
                    onClick={() => window.open('/cfg.html', '_blank')}
                    className="w-full py-3 px-4 rounded-xl bg-slate-800 border border-slate-700 text-slate-300 hover:text-white hover:bg-slate-700 transition-all text-sm font-semibold flex items-center justify-center gap-2"
                >
                    Control Flow Graph
                </button>
            </div>
        </aside>
    );
};

const TimingItem = ({ label, value }) => (
    <div className="flex flex-col gap-1">
        <div className="flex justify-between items-center text-[10px] font-medium font-mono">
            <span className="text-slate-400 capitalize">{label.replace(/_/g, ' ')}</span>
            <span className="text-blue-400">{value}s</span>
        </div>
        <div className="h-1 w-full bg-slate-800 rounded-full overflow-hidden">
            <div
                className="h-full bg-blue-500 rounded-full transition-all duration-1000"
                style={{ width: `${Math.min((value / 15) * 100, 100)}%` }}
            />
        </div>
    </div>
);

const DebugSection = ({ title, content, isCode }) => (
    <div className="space-y-2">
        <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">{title}</h3>
        <div className="bg-black/40 border border-slate-800 rounded-lg p-3 max-h-60 overflow-y-auto">
            <pre className={`text-[11px] leading-relaxed ${isCode ? 'text-purple-300' : 'text-slate-300'} whitespace-pre-wrap break-all font-mono`}>
                {content}
            </pre>
        </div>
    </div>
);

export default DebugPanel;
