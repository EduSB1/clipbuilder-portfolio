import { useState, useRef } from "react";
import {
    Upload,
    FileText,
    AlertCircle,
    CheckCircle,
    X,
    Archive,
} from "lucide-react";
import { parseMarkdown, validateSchema } from "../../utils/markdownUtils";

export default function ImportMarkdownModal({ open, onClose, onImport }) {
    const [file, setFile] = useState(null);
    const [content, setContent] = useState("");
    const [parsed, setParsed] = useState(null);
    const [validation, setValidation] = useState(null);
    const [error, setError] = useState("");
    const [images, setImages] = useState({}); // { imageName: blob }
    const [isZip, setIsZip] = useState(false);
    const fileInputRef = useRef(null);

    if (!open) return null;

    const handleFileChange = async (e) => {
        setError("");
        setParsed(null);
        setValidation(null);
        setImages({});
        setIsZip(false);

        const selectedFile = e.target.files?.[0];
        if (!selectedFile) return;

        const fileName = selectedFile.name.toLowerCase();

        if (fileName.endsWith(".zip")) {
            setIsZip(true);
            setFile(selectedFile);
            await processZipFile(selectedFile);
        } else if (fileName.endsWith(".md")) {
            setFile(selectedFile);
            try {
                const text = await selectedFile.text();
                setContent(text);
                processMarkdown(text);
            } catch (err) {
                setError(
                    "Erro ao ler o arquivo: " + (err.message || "Desconhecido"),
                );
            }
        } else {
            setError("Por favor, selecione um arquivo .md ou .zip");
        }
    };

    const processZipFile = async (zipFile) => {
        try {
            const JSZip = (await import("jszip")).default;
            const zip = await JSZip.loadAsync(zipFile);

            let markdownContent = "";
            const extractedImages = {};

            for (const [filename, fileEntry] of Object.entries(zip.files)) {
                if (fileEntry.dir) continue;

                if (filename.endsWith(".md")) {
                    markdownContent = await fileEntry.async("string");
                } else if (filename.match(/\.(png|jpg|jpeg|gif|webp)$/i)) {
                    const blob = await fileEntry.async("blob");
                    const imageName = filename.split("/").pop();
                    extractedImages[imageName] = blob;
                }
            }

            if (!markdownContent) {
                setError("Nenhum arquivo .md encontrado no ZIP");
                return;
            }

            setContent(markdownContent);
            setImages(extractedImages);
            processMarkdown(markdownContent);
        } catch (err) {
            setError(
                "Erro ao processar ZIP: " + (err.message || "Desconhecido"),
            );
        }
    };

    const processMarkdown = (text) => {
        const result = parseMarkdown(text);
        setParsed(result);
        const valid = validateSchema(result);
        setValidation(valid);
    };

    const handleImport = () => {
        if (!parsed || !validation?.valid) return;
        onImport(parsed, content, images);
        handleClose();
    };

    const handleClose = () => {
        setFile(null);
        setContent("");
        setParsed(null);
        setValidation(null);
        setError("");
        setImages({});
        setIsZip(false);
        onClose();
    };

    const handleDrop = (e) => {
        e.preventDefault();
        const droppedFile = e.dataTransfer.files?.[0];
        if (droppedFile) {
            const input = fileInputRef.current;
            const dt = new DataTransfer();
            dt.items.add(droppedFile);
            input.files = dt.files;
            handleFileChange({ target: { files: dt.files } });
        }
    };

    const imageCount = Object.keys(images).length;

    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center p-4"
            style={{ backgroundColor: "rgba(0, 0, 0, 0.6)" }}
            onClick={handleClose}
        >
            <div
                className="w-full max-w-lg rounded-xl shadow-2xl"
                style={{
                    backgroundColor: "var(--card-bg)",
                    border: "1px solid var(--card-border)",
                }}
                onClick={(e) => e.stopPropagation()}
            >
                {/* Header */}
                <div
                    className="flex items-center justify-between p-4 border-b"
                    style={{ borderColor: "var(--card-border)" }}
                >
                    <div className="flex items-center gap-2">
                        <FileText
                            className="h-5 w-5"
                            style={{ color: "var(--primary)" }}
                        />
                        <h2 className="text-lg font-semibold">
                            Importar Documentação
                        </h2>
                    </div>
                    <button
                        onClick={handleClose}
                        className="p-1 rounded-lg hover:bg-black/10 transition-colors"
                    >
                        <X className="h-5 w-5" />
                    </button>
                </div>

                {/* Content */}
                <div className="p-4 space-y-4">
                    {/* Drop Zone */}
                    <div
                        className="border-2 border-dashed rounded-lg p-8 text-center transition-colors cursor-pointer"
                        style={{
                            borderColor: file
                                ? "var(--primary)"
                                : "var(--card-border)",
                            backgroundColor: file
                                ? "var(--primary-bg)"
                                : "transparent",
                        }}
                        onClick={() => fileInputRef.current?.click()}
                        onDragOver={(e) => e.preventDefault()}
                        onDrop={handleDrop}
                    >
                        <input
                            ref={fileInputRef}
                            type="file"
                            accept=".md,.zip"
                            onChange={handleFileChange}
                            className="hidden"
                        />
                        {isZip ? (
                            <Archive
                                className="h-10 w-10 mx-auto mb-3"
                                style={{ color: "var(--text-secondary)" }}
                            />
                        ) : (
                            <Upload
                                className="h-10 w-10 mx-auto mb-3"
                                style={{ color: "var(--text-secondary)" }}
                            />
                        )}
                        {file ? (
                            <p
                                className="font-medium"
                                style={{ color: "var(--primary)" }}
                            >
                                {file.name}
                            </p>
                        ) : (
                            <>
                                <p className="font-medium">
                                    Arraste um arquivo .md ou .zip aqui
                                </p>
                                <p
                                    className="text-sm mt-1"
                                    style={{ color: "var(--text-secondary)" }}
                                >
                                    ou clique para selecionar
                                </p>
                            </>
                        )}
                    </div>

                    {/* Error */}
                    {error && (
                        <div
                            className="flex items-center gap-2 p-3 rounded-lg"
                            style={{
                                backgroundColor: "var(--danger-bg)",
                                color: "var(--danger)",
                            }}
                        >
                            <AlertCircle className="h-4 w-4 flex-shrink-0" />
                            <span className="text-sm">{error}</span>
                        </div>
                    )}

                    {/* Validation Errors */}
                    {validation && !validation.valid && (
                        <div
                            className="p-3 rounded-lg"
                            style={{
                                backgroundColor: "var(--warning-bg)",
                                color: "var(--warning)",
                            }}
                        >
                            <div className="flex items-center gap-2 mb-2">
                                <AlertCircle className="h-4 w-4" />
                                <span className="font-medium text-sm">
                                    Schema inválido
                                </span>
                            </div>
                            <ul className="text-sm list-disc list-inside space-y-1">
                                {validation.errors.map((err, idx) => (
                                    <li key={idx}>{err}</li>
                                ))}
                            </ul>
                        </div>
                    )}

                    {/* Preview */}
                    {parsed && validation?.valid && (
                        <div
                            className="p-4 rounded-lg"
                            style={{
                                backgroundColor: "var(--bg)",
                                border: "1px solid var(--card-border)",
                            }}
                        >
                            <div className="flex items-center gap-2 mb-3">
                                <CheckCircle
                                    className="h-4 w-4"
                                    style={{ color: "var(--success)" }}
                                />
                                <span
                                    className="font-medium text-sm"
                                    style={{ color: "var(--success)" }}
                                >
                                    Arquivo válido
                                </span>
                            </div>

                            <div className="space-y-2 text-sm">
                                <div className="flex justify-between">
                                    <span
                                        style={{
                                            color: "var(--text-secondary)",
                                        }}
                                    >
                                        Título:
                                    </span>
                                    <span className="font-medium">
                                        {parsed.metadata.title || "Sem título"}
                                    </span>
                                </div>
                                <div className="flex justify-between">
                                    <span
                                        style={{
                                            color: "var(--text-secondary)",
                                        }}
                                    >
                                        Status:
                                    </span>
                                    <span className="font-medium">
                                        {parsed.metadata.status || "N/A"}
                                    </span>
                                </div>
                                <div className="flex justify-between">
                                    <span
                                        style={{
                                            color: "var(--text-secondary)",
                                        }}
                                    >
                                        Passos:
                                    </span>
                                    <span className="font-medium">
                                        {parsed.steps.length}
                                    </span>
                                </div>
                                <div className="flex justify-between">
                                    <span
                                        style={{
                                            color: "var(--text-secondary)",
                                        }}
                                    >
                                        Último concluído:
                                    </span>
                                    <span className="font-medium">
                                        {parsed.metadata.lastCompletedStep || 0}
                                    </span>
                                </div>
                                {imageCount > 0 && (
                                    <div className="flex justify-between">
                                        <span
                                            style={{
                                                color: "var(--text-secondary)",
                                            }}
                                        >
                                            Imagens encontradas:
                                        </span>
                                        <span
                                            className="font-medium"
                                            style={{ color: "var(--success)" }}
                                        >
                                            {imageCount}
                                        </span>
                                    </div>
                                )}
                            </div>
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div
                    className="flex justify-end gap-3 p-4 border-t"
                    style={{ borderColor: "var(--card-border)" }}
                >
                    <button onClick={handleClose} className="cb-btn px-4 py-2">
                        Cancelar
                    </button>
                    <button
                        onClick={handleImport}
                        disabled={!parsed || !validation?.valid}
                        className="cb-btn cb-btn-primary px-4 py-2 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        Importar Documentação
                    </button>
                </div>
            </div>
        </div>
    );
}
