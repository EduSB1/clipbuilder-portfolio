import { useEffect, useRef } from "react";
import styles from "./login.module.css";

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

export default function LoginBackground() {
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
            for (const blob of AURORA_BLOBS) {
                const px = (blob.bx + Math.sin(timeMs * blob.speed + blob.phase) * 0.14) * width;
                const py = (blob.by + Math.cos(timeMs * blob.speed + blob.phase) * 0.1) * height;
                const pulse = Math.sin(elapsed * 1.4 + blob.phase) * 0.015;
                const alpha = clamp(blob.baseAlpha + pulse, 0.01, 0.16);
                const gradient = ctx.createRadialGradient(px, py, 0, px, py, blob.r);
                gradient.addColorStop(0, `rgba(${blob.color[0]}, ${blob.color[1]}, ${blob.color[2]}, ${alpha})`);
                gradient.addColorStop(0.58, `rgba(${blob.color[0]}, ${blob.color[1]}, ${blob.color[2]}, ${alpha * 0.34})`);
                gradient.addColorStop(1, `rgba(${blob.color[0]}, ${blob.color[1]}, ${blob.color[2]}, 0)`);
                ctx.fillStyle = gradient;
                ctx.fillRect(0, 0, width, height);
            }
        };

        const updateGrid = (timeMs) => {
            const drawLink = (a, b) => {
                if (!a || !b) return;
                const nearA = Math.hypot(a.x - mouse.x, a.y - mouse.y);
                const nearB = Math.hypot(b.x - mouse.x, b.y - mouse.y);
                const proximity = mouse.active ? clamp(1 - Math.min(nearA, nearB) / 180, 0, 1) : 0;
                const alpha = 0.06 + proximity * 0.34;
                ctx.strokeStyle = `rgba(10, 93, 115, ${alpha})`;
                ctx.lineWidth = 0.7 + proximity * 0.45;
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

                node.vx *= 0.82;
                node.vy *= 0.82;
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
                const near = mouse.active ? clamp(1 - distance / 130, 0, 1) : 0;
                const radius = near > 0.04 ? 2.2 : 1.2;
                if (near > 0.08) {
                    ctx.shadowBlur = 12 + near * 10;
                    ctx.shadowColor = "rgba(10, 93, 115, 0.35)";
                } else {
                    ctx.shadowBlur = 0;
                }
                ctx.fillStyle = `rgba(10, 93, 115, ${0.21 + near * 0.65})`;
                ctx.beginPath();
                ctx.arc(node.x, node.y, radius, 0, Math.PI * 2);
                ctx.fill();
            }
            ctx.shadowBlur = 0;
        };

        const updateParticles = (timeMs) => {
            for (const particle of particles) {
                particle.y -= particle.speed;
                particle.x += particle.drift + Math.sin(timeMs * 0.0013 + particle.phase) * 0.18;
                particle.life = Math.min(1, particle.life + particle.lifeSpeed);
                const alpha = Math.sin(particle.life * Math.PI) * particle.alpha;

                ctx.fillStyle = `rgba(10, 93, 115, ${alpha})`;
                ctx.beginPath();
                ctx.arc(particle.x, particle.y, particle.size, 0, Math.PI * 2);
                ctx.fill();

                if (particle.y < -22) {
                    resetParticle(particle, width, height);
                }
            }
        };

        const drawScan = () => {
            const y = (elapsed * 26) % (height + 60) - 30;
            const gradient = ctx.createLinearGradient(0, y - 30, 0, y + 30);
            gradient.addColorStop(0, "rgba(10, 93, 115, 0)");
            gradient.addColorStop(0.5, "rgba(10, 93, 115, 0.028)");
            gradient.addColorStop(1, "rgba(10, 93, 115, 0)");
            ctx.fillStyle = gradient;
            ctx.fillRect(0, y - 30, width, 60);
        };

        const frame = (timeMs) => {
            const dt = (timeMs - lastTime) / 1000;
            lastTime = timeMs;
            elapsed += dt;

            const isLight = document.documentElement.classList.contains("light");

            ctx.clearRect(0, 0, width, height);
            ctx.fillStyle = isLight ? "#F8FAFC" : "#060a0e";
            ctx.fillRect(0, 0, width, height);

            // Adjust aurora opacity for light mode
            const originalBlobs = AURORA_BLOBS.map(b => ({ ...b }));
            if (isLight) {
                AURORA_BLOBS.forEach(b => {
                    b.baseAlpha *= 0.6; // Softer in light mode
                });
            }

            drawAurora(timeMs);
            
            // Restore blobs for next frame check
            originalBlobs.forEach((b, i) => {
                AURORA_BLOBS[i].baseAlpha = b.baseAlpha;
            });

            updateGrid(timeMs);
            updateParticles(timeMs);
            drawScan();

            glow.gx += (glow.tx - glow.gx) * 0.12;
            glow.gy += (glow.ty - glow.gy) * 0.12;
            halo.style.transform = `translate3d(${glow.gx - 180}px, ${glow.gy - 180}px, 0)`;

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
        <>
            <canvas ref={canvasRef} className={styles.backgroundCanvas} aria-hidden="true" />
            <div ref={haloRef} className={styles.cursorHalo} aria-hidden="true" />
        </>
    );
}
