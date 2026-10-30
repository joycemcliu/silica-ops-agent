package secrets

import "errors"

// Registrar is implemented by redact.Redactor. Keeping the dependency as an
// interface also allows a future Vault backend to reuse this wrapper.
type Registrar interface{ AddSecret(string) }

type registered struct {
	store    Store
	redactor Registrar
}

// WithRedaction ensures every retrieved credential is registered for literal
// redaction before any consumer can use it in a connection or error.
func WithRedaction(store Store, redactor Registrar) Store {
	return &registered{store: store, redactor: redactor}
}

func (s *registered) Get(ref string) (string, error) {
	value, err := s.store.Get(ref)
	if err != nil {
		// Future backends may include connection details in their errors.
		return "", errors.New("secret unavailable")
	}
	s.redactor.AddSecret(value)
	return value, nil
}
