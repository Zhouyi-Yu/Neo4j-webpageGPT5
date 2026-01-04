import React from 'react';

const Logo = () => {
    return (
        <div className="fixed bottom-6 left-6 w-[250px] z-10 pointer-events-none select-none flex flex-col items-end opacity-100">
            <img
                src="/logos/txtProceed.png"
                alt="Top Logo"
                className="w-1/2 block mb-[10px] mt-[40px]"
            />
            <img
                src="/logos/logoProceed.png"
                alt="Logo"
                className="w-[70%] block"
            />
        </div>
    );
};

export default Logo;