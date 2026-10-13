import React, { useEffect, useRef, useState } from "react";

const MAX_TILT = 6; // Subtler for dashboard than login

export default function MouseTilt({ children, className = "", style = {} }) {
  const containerRef = useRef(null);
  
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const target = { x: 0, y: 0, mx: 50, my: 50 };
    const current = { x: 0, y: 0, mx: 50, my: 50 };
    let rafId = 0;

    const onMove = (e) => {
      const rect = container.getBoundingClientRect();
      const x = (e.clientX - rect.left) / rect.width - 0.5;
      const y = (e.clientY - rect.top) / rect.height - 0.5;
      
      target.x = -y * MAX_TILT;
      target.y = x * MAX_TILT;
      target.mx = ((e.clientX - rect.left) / rect.width) * 100;
      target.my = ((e.clientY - rect.top) / rect.height) * 100;
    };

    const onLeave = () => {
      target.x = 0;
      target.y = 0;
      target.mx = 50;
      target.my = 50;
    };

    const frame = () => {
      current.x += (target.x - current.x) * 0.1;
      current.y += (target.y - current.y) * 0.1;
      current.mx += (target.mx - current.mx) * 0.1;
      current.my += (target.my - current.my) * 0.1;

      if (container) {
        container.style.transform = `perspective(1000px) rotateX(${current.x.toFixed(2)}deg) rotateY(${current.y.toFixed(2)}deg)`;
        container.style.setProperty("--mx", `${current.mx.toFixed(2)}%`);
        container.style.setProperty("--my", `${current.my.toFixed(2)}%`);
      }
      
      rafId = requestAnimationFrame(frame);
    };

    container.addEventListener("mousemove", onMove);
    container.addEventListener("mouseleave", onLeave);
    rafId = requestAnimationFrame(frame);

    return () => {
      cancelAnimationFrame(rafId);
      container.removeEventListener("mousemove", onMove);
      container.removeEventListener("mouseleave", onLeave);
    };
  }, []);

  return (
    <div
      ref={containerRef}
      className={className}
      style={{
        ...style,
        transition: "box-shadow 0.3s ease",
        willChange: "transform",
        transformStyle: "preserve-3d",
      }}
    >
      {children}
    </div>
  );
}
