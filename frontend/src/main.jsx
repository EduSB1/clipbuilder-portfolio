import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App.jsx";
import { AppAuthProvider } from "./utils/AuthContext.jsx";
import ErrorBoundary from "./components/shared/ErrorBoundary.jsx";
import { ClerkProvider } from "@clerk/clerk-react";
import { ptBR } from "@clerk/localizations";
import "./index.css";

const DEV = import.meta.env.DEV;
const CLERK_PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

if (DEV) {
  console.log("ClipBuilder: main.jsx start");
  console.log(
    "ClipBuilder: CLERK_PUBLISHABLE_KEY length =",
    CLERK_PUBLISHABLE_KEY?.length || 0,
  );
}

function isClerkDisabled() {
  try {
    return localStorage.getItem("CLIPBUILDER_DISABLE_CLERK") === "1";
  } catch {
    return false;
  }
}

const rootElement = document.getElementById("root");
if (DEV) console.log("ClipBuilder: rootElement found =", !!rootElement);

if (!rootElement) {
    console.error("ClipBuilder: CRITICAL - #root element not found!");
} else {
    const root = ReactDOM.createRoot(rootElement);
    
    root.render(
        <React.StrictMode>
            <ErrorBoundary>
                <BrowserRouter>
                    {CLERK_PUBLISHABLE_KEY && !isClerkDisabled() ? (
                        <ClerkProvider
                            publishableKey={CLERK_PUBLISHABLE_KEY}
                            localization={ptBR}
                            afterSignOutUrl="/login"
                        >
                            <AppAuthProvider>
                                <App />
                            </AppAuthProvider>
                        </ClerkProvider>
                    ) : (
                        <AppAuthProvider>
                            <App />
                        </AppAuthProvider>
                    )}
                </BrowserRouter>
            </ErrorBoundary>
        </React.StrictMode>
    );
    if (DEV) console.log("ClipBuilder: root.render called");
}
