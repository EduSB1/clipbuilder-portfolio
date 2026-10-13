import React from "react";
const logoImg = "/icon.png";

function LogoMark({ size = 22, color = "currentColor" }) {
    return (
        <svg
            width={size}
            height={size}
            viewBox="0 0 36 36"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            aria-hidden="true"
            focusable="false"
            style={{ display: "block" }}
        >
            <rect
                x="2"
                y="6"
                width="32"
                height="24"
                rx="4"
                stroke={color}
                strokeWidth="2"
                fill="none"
            />
            <rect
                x="2"
                y="6"
                width="32"
                height="7"
                rx="4"
                fill={color}
                opacity="0.15"
            />
            <line x1="10" y1="6" x2="8" y2="13" stroke={color} strokeWidth="1.5" />
            <line x1="18" y1="6" x2="16" y2="13" stroke={color} strokeWidth="1.5" />
            <line x1="26" y1="6" x2="24" y2="13" stroke={color} strokeWidth="1.5" />
            <polygon points="15,19 15,27 23,23" fill={color} opacity="0.9" />
        </svg>
    );
}

export default function Logo({ size = 32, showText = true }) {
    const iconSize = Math.max(24, Number(size) || 32);
    return (
        <div
            className="logo-wrapper group cursor-pointer transition-transform duration-300 hover:scale-[1.03]"
            style={{
                display: "flex",
                alignItems: "center",
                gap: "10px",
                userSelect: "none",
            }}
        >
            <div
                className="logo-icon"
                style={{
                    width: iconSize,
                    height: iconSize,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    flexShrink: 0,
                }}
            >
                <img
                    src={logoImg}
                    alt="ClipBuilder logo"
                    style={{ width: "100%", height: "100%", objectFit: "contain" }}
                />
            </div>
            {showText ? (
                <span
                    style={{
                        fontFamily: "DM Sans, sans-serif",
                        fontSize: Math.round(iconSize * 0.72),
                        color: "var(--text-primary)",
                        letterSpacing: "-0.03em",
                        lineHeight: 1,
                    }}
                >
                    <span style={{ fontWeight: 400 }}>ClipBuilder</span>
                </span>
            ) : null}
        </div>
    );
}
