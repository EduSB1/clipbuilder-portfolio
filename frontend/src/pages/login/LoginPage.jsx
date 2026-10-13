import LoginBackground from "./LoginBackground";
import LoginForm from "./LoginForm";
import styles from "./login.module.css";

export default function LoginPage() {
    return (
        <div className={styles.loginRoot}>
            <LoginBackground />
            <div className={styles.backdropVignette} aria-hidden="true" />
            <main className={styles.loginMain}>
                <LoginForm />
            </main>
        </div>
    );
}
