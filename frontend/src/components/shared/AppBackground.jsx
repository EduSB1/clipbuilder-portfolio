import { useEffect, useRef } from "react";

const AURORA_BLOBS = [
    { bx: 0.22, by: 0.28, r: 480, baseAlpha: 0.072, speed: 0.00028, phase: 0, color: [10, 93, 115] },
    { bx: 0.78, by: 0.62, r: 380, baseAlpha: 0.05, speed: 0.00038, phase: 2, color: [8, 77, 94] },
    { bx: 0.5, by: 0.85, r: 320, baseAlpha: 0.038, speed: 0.0005, phase: 4.3, color: [12, 77, 94] },
    { bx: 0.15, by: 0.72, r: 260, baseAlpha: 0.03, speed: 0.00042, phase: 1.5, color: [10, 93, 115] },
];

const GRID_COLS = 18;
const GRID_ROWS = 12;
const PARTICLE_COUNT = 60; 

const clamp = (v, min, max) => Math.max(min, Math.min(max, v));
const rand = (min, max) => min + Math.random() * (max - min);

function resetParticle(particle, width, height) {
    particle.x = rand(0, width);
    particle.y = height + rand(6, 160);
    particle.speed = rand(0.28, 1.08);
    particle.drift = rand(-0.25, 0.25);
    particle.life = 0;
    particle.lifeSpeed = rand(0.004, 0.013);
    particle.size = rand(0.75, 1.95);
    particle.alpha = rand(0.08, 0.38);
    particle.phase = rand(0, Math.PI * 2);
}

function buildGrid(width, height) {
    const nodes = [];
    for (let row = 0; row < GRID_ROWS; row += 1) {
        for (let col = 0; col < GRID_COLS; col += 1) {
            const u = col / (GRID_COLS - 1);
            const v = row / (GRID_ROWS - 1);
            nodes.push({
                col,
                row,
                u,
                v,
                x: u * width,
                y: v * height,
                vx: 0,
                vy: 0,
                phase: rand(0, Math.PI * 2),
                phase2: rand(0, Math.PI * 2),
            });
        }
    }
    return nodes;
}

export default function AppBackground() {
    const canvasRef = useRef(null);
    const haloRef = useRef(null);

    useEffect(() => {
        const canvas = canvasRef.current;
        const halo = haloRef.current;
        if (!canvas || !halo) return undefined;

        const ctx = canvas.getContext("2d");
        if (!ctx) return undefined;

        let width = window.innerWidth;
        let height = window.innerHeight;
        let dpr = Math.min(window.devicePixelRatio || 1, 2);
        let rafId = 0;
        let elapsed = 0;
        let lastTime = performance.now();
        let nodes = buildGrid(width, height);
        const particles = Array.from({ length: PARTICLE_COUNT }, () => ({}));

        const mouse = { x: width * 0.5, y: height * 0.5, active: false };
        const glow = { tx: width * 0.5, ty: height * 0.5, gx: width * 0.5, gy: height * 0.5 };

        // Helper to check current theme
        const isLight = () => document.documentElement.classList.contains("light");

        const setupCanvas = () => {
            width = window.innerWidth;
            height = window.innerHeight;
            dpr = Math.min(window.devicePixelRatio || 1, 2);
            canvas.width = Math.floor(width * dpr);
            canvas.height = Math.floor(height * dpr);
            canvas.style.width = `${width}px`;
            canvas.style.height = `${height}px`;
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
            nodes = buildGrid(width, height);
            particles.forEach((particle) => resetParticle(particle, width, height));
            if (!mouse.active) {
                mouse.x = width * 0.5;
                mouse.y = height * 0.5;
                glow.tx = mouse.x;
                glow.ty = mouse.y;
            }
        };

        const onMouseMove = (event) => {
            mouse.x = event.clientX;
            mouse.y = event.clientY;
            mouse.active = true;
            glow.tx = event.clientX;
            glow.ty = event.clientY;
        };

        const onMouseLeave = () => {
            mouse.active = false;
            glow.tx = width * 0.5;
            glow.ty = height * 0.5;
        };

        const drawAurora = (timeMs) => {
            const light = isLight();
            const alphaMultiplier = light ? 0.35 : 1.0; // Reduce visibility in light mode
            const accentColor = light ? [0, 98, 105] : [0, 98, 105];
            
            for (const blob of AURORA_BLOBS) {
                const px = (blob.bx + Math.sin(timeMs * blob.speed + blob.phase) * 0.14) * width;
                const py = (blob.by + Math.cos(timeMs * blob.speed + blob.phase) * 0.1) * height;
                const pulse = Math.sin(elapsed * 1.4 + blob.phase) * 0.015;
                const alpha = clamp(blob.baseAlpha + pulse, 0.01, 0.16) * alphaMultiplier;
                
                // Use the theme-aware accent color
                const color = accentColor;
                
                const gradient = ctx.createRadialGradient(px, py, 0, px, py, blob.r);
                gradient.addColorStop(0, `rgba(${color[0]}, ${color[1]}, ${color[2]}, ${alpha})`);
                gradient.addColorStop(0.58, `rgba(${color[0]}, ${color[1]}, ${color[2]}, ${alpha * 0.34})`);
                gradient.addColorStop(1, `rgba(${color[0]}, ${color[1]}, ${color[2]}, 0)`);
                ctx.fillStyle = gradient;
                ctx.fillRect(0, 0, width, height);
            }
        };

        const updateGrid = (timeMs) => {
            const light = isLight();
            const accentColor = light ? "6, 62, 77" : "6, 62, 77";
            const baseAlpha = light ? 0.03 : 0.05;

            const drawLink = (a, b) => {
                if (!a || !b) return;
                const nearA = Math.hypot(a.x - mouse.x, a.y - mouse.y);
                const nearB = Math.hypot(b.x - mouse.x, b.y - mouse.y);
                const proximity = mouse.active ? clamp(1 - Math.min(nearA, nearB) / 180, 0, 1) : 0;
                const alpha = (light ? 0.04 : 0.06) + proximity * 0.34;
                
                ctx.strokeStyle = `rgba(${accentColor}, ${alpha})`;
                ctx.lineWidth = (light ? 0.5 : 0.7) + proximity * 0.45;
                ctx.beginPath();
                ctx.moveTo(a.x, a.y);
                ctx.lineTo(b.x, b.y);
                ctx.stroke();
            };

            for (const node of nodes) {
                const wobbleX =
                    Math.sin(timeMs * 0.00072 + node.phase) * 10 +
                    Math.cos(timeMs * 0.00038 + node.phase2) * 8;
                const wobbleY =
                    Math.cos(timeMs * 0.00067 + node.phase) * 8 +
                    Math.sin(timeMs * 0.00044 + node.phase2) * 9;
                const baseX = node.u * width + wobbleX;
                const baseY = node.v * height + wobbleY;
                const projectedX = baseX + node.vx;
                const projectedY = baseY + node.vy;

                if (mouse.active) {
                    const dx = projectedX - mouse.x;
                    const dy = projectedY - mouse.y;
                    const distance = Math.hypot(dx, dy);
                    if (distance < 130) {
                        const intensity = (1 - distance / 130) * 1.85;
                        node.vx += (dx / (distance || 1)) * intensity;
                        node.vy += (dy / (distance || 1)) * intensity;
                    }
                }

                node.vx *= 0.85;
                node.vy *= 0.85;
                node.x = baseX + node.vx;
                node.y = baseY + node.vy;
            }

            for (const node of nodes) {
                const right = nodes[node.row * GRID_COLS + node.col + 1];
                const bottom = nodes[(node.row + 1) * GRID_COLS + node.col];
                drawLink(node, right);
                drawLink(node, bottom);
            }

            for (const node of nodes) {
                const distance = Math.hypot(node.x - mouse.x, node.y - mouse.y);
                const near = mouse.active ? clamp(1 - distance / 200, 0, 1) : 0;
                const radius = near > 0.04 ? 2.0 : 1.0;
                
                if (near > 0.08) {
                    ctx.shadowBlur = light ? 4 : 8 + near;
                    ctx.shadowColor = `rgba(${accentColor}, 0.2)`;
                } else {
                    ctx.shadowBlur = 0;
                }
                ctx.fillStyle = `rgba(${accentColor}, ${baseAlpha + 0.1 + near * 0.5})`;
                ctx.beginPath();
                ctx.arc(node.x, node.y, radius, 0, Math.PI * 2);
                ctx.fill();
            }
            ctx.shadowBlur = 0;
        };

        const updateParticles = (timeMs) => {
            const light = isLight();
            const accentColor = light ? "0, 139, 148" : "10, 93, 115";
            const particleAlphaMult = light ? 0.4 : 1.0;

            for (const particle of particles) {
                particle.y -= particle.speed;
                particle.x += particle.drift + Math.sin(timeMs * 0.0013 + particle.phase) * 0.15;
                particle.life = Math.min(1, particle.life + particle.lifeSpeed);
                const alpha = Math.sin(particle.life * Math.PI) * particle.alpha * particleAlphaMult;

                ctx.fillStyle = `rgba(${accentColor}, ${alpha})`;
                ctx.beginPath();
                ctx.arc(particle.x, particle.y, particle.size, 0, Math.PI * 2);
                ctx.fill();

                if (particle.y < -22) {
                    resetParticle(particle, width, height);
                }
            }
        };

        const drawScan = () => {
            const light = isLight();
            const y = (elapsed * 26) % (height + 60) - 30;
            const gradient = ctx.createLinearGradient(0, y - 30, 0, y + 30);
            const scanColor = light ? "0, 139, 148" : "10, 93, 115";
            const scanAlpha = light ? 0.01 : 0.025;
            
            gradient.addColorStop(0, `rgba(${scanColor}, 0)`);
            gradient.addColorStop(0.5, `rgba(${scanColor}, ${scanAlpha})`);
            gradient.addColorStop(1, `rgba(${scanColor}, 0)`);
            ctx.fillStyle = gradient;
            ctx.fillRect(0, y - 30, width, 60);
        };

        const frame = (timeMs) => {
            const dt = (timeMs - lastTime) / 1000;
            lastTime = timeMs;
            elapsed += dt;

            ctx.clearRect(0, 0, width, height);
            
            // Fill background with theme-based color
            const light = isLight();
            ctx.fillStyle = light ? "#F8FAFC" : "#060a0e"; // Match login bg
            ctx.fillRect(0, 0, width, height);
            
            if (!light) {
                // Add the subtle top glow from login page
                const grad = ctx.createRadialGradient(width/2, -height*0.15, 0, width/2, -height*0.15, height*0.6);
                grad.addColorStop(0, "#0f2032");
                grad.addColorStop(1, "#060a0e");
                ctx.fillStyle = grad;
                ctx.fillRect(0, 0, width, height);
            }

            drawAurora(timeMs);
            updateGrid(timeMs);
            updateParticles(timeMs);
            drawScan();

            glow.gx += (glow.tx - glow.gx) * 0.12;
            glow.gy += (glow.ty - glow.gy) * 0.12;
            
            if (halo) {
              // Center it properly for 360px halo (login pattern)
              halo.style.transform = `translate3d(${glow.gx - 180}px, ${glow.gy - 180}px, 0)`;
              halo.style.opacity = mouse.active ? (light ? "0.45" : "1") : "0";
            }

            rafId = requestAnimationFrame(frame);
        };

        setupCanvas();
        window.addEventListener("resize", setupCanvas);
        window.addEventListener("mousemove", onMouseMove);
        window.addEventListener("mouseleave", onMouseLeave);
        rafId = requestAnimationFrame(frame);

        return () => {
            cancelAnimationFrame(rafId);
            window.removeEventListener("resize", setupCanvas);
            window.removeEventListener("mousemove", onMouseMove);
            window.removeEventListener("mouseleave", onMouseLeave);
        };
    }, []);

    return (
        <div className="app-background-container">
            <div className="app-background-vignette" aria-hidden="true" />
            <canvas ref={canvasRef} className="app-background-canvas" aria-hidden="true" />
            <div ref={haloRef} className="app-background-halo" aria-hidden="true" />
        </div>
    );
}
