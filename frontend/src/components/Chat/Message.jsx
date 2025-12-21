import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Copy, Check } from 'lucide-react';
import { cn } from '../../lib/utils';

const Message = ({ role, content, children }) => {
    const [copied, setCopied] = useState(false);

    const handleCopy = () => {
        navigator.clipboard.writeText(content).then(() => {
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        });
    };

    return (
        <div
            className={cn(
                "max-w-[85%] p-4 rounded-2xl relative animate-in fade-in slide-in-from-bottom-2 duration-300",
                role === 'user'
                    ? "self-end bg-slate-800 text-slate-100 rounded-br-sm"
                    : "self-start bg-blue-950 text-slate-100 rounded-bl-sm border border-blue-900/50"
            )}
        >
            <div className="prose prose-invert prose-sm max-w-none">
                <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={{
                        a: ({ node, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer" className="text-blue-400 underline hover:text-blue-300" />
                    }}
                >
                    {content}
                </ReactMarkdown>
            </div>

            {children}

            {role === 'assistant' && content && (
                <button
                    onClick={handleCopy}
                    className="mt-3 flex items-center gap-2 text-xs py-1.5 px-3 rounded-lg bg-slate-800/50 border border-slate-700 hover:bg-slate-700 hover:text-white transition-all shadow-sm"
                >
                    {copied ? (
                        <>
                            <Check size={14} className="text-green-400" />
                            <span>Copied!</span>
                        </>
                    ) : (
                        <>
                            <Copy size={14} />
                            <span>Copy</span>
                        </>
                    )}
                </button>
            )}
        </div>
    );
};

export default Message;
