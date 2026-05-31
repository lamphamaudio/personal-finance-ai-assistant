export default function Login() {
  return (
    <main className="login-screen">
      <section className="login-panel">
        <div>
          <p className="eyebrow">Secure access</p>
          <h1>Spectra</h1>
          <p className="muted">
            Sign in through Bank Simulator to connect your demo bank profile.
          </p>
        </div>

        <a className="primary-btn bank-signin" href="/sso/bank">
          Sign in with Bank
        </a>
      </section>
    </main>
  );
}
