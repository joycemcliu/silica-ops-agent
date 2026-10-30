package secrets

import (
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"ops-agent/broker/internal/redact"
)

func TestEnvironmentAndRedactionRegistration(t *testing.T) {
	t.Setenv("OPS_TEST_SYNTHETIC", "standalone-synthetic-credential")
	r, err := redact.New(nil)
	if err != nil {
		t.Fatal(err)
	}
	local, err := NewLocal("")
	if err != nil {
		t.Fatal(err)
	}
	defer local.Close()
	store := WithRedaction(local, r)
	value, err := store.Get("env:OPS_TEST_SYNTHETIC")
	if err != nil || value != "standalone-synthetic-credential" {
		t.Fatal("secret read failed")
	}
	if strings.Contains(r.String("unlabelled "+value), value) {
		t.Fatal("retrieved secret not registered")
	}
	for _, ref := range []string{"inline-password", "env:missing", "env:", "vault:test", "file:secret"} {
		if _, err := store.Get(ref); err == nil || strings.Contains(err.Error(), ref) {
			t.Fatal("unsafe or missing rejection")
		}
	}
}

func TestFileConfinementAndPermissions(t *testing.T) {
	root := t.TempDir()
	outside := filepath.Join(t.TempDir(), "outside")
	if err := os.WriteFile(outside, []byte("synthetic-outside"), 0600); err != nil {
		t.Fatal(err)
	}
	for name, mode := range map[string]os.FileMode{"valid": 0600, "public": 0644} {
		if err := os.WriteFile(filepath.Join(root, name), []byte("synthetic-secret\n"), mode); err != nil {
			t.Fatal(err)
		}
	}
	if err := os.Symlink(outside, filepath.Join(root, "escape")); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "large"), []byte(strings.Repeat("x", MaxBytes+1)), 0600); err != nil {
		t.Fatal(err)
	}
	s, err := NewLocal(root)
	if err != nil {
		t.Fatal(err)
	}
	defer s.Close()
	if value, err := s.Get("file:valid"); err != nil || value != "synthetic-secret\n" {
		t.Fatal("file bytes not preserved")
	}
	for _, ref := range []string{"file:../outside", "file:/etc/passwd", "file:escape", "file:public", "file:.", "file:missing", "file:large", "file:valid/../valid", "file:valid\\other"} {
		if _, err := s.Get(ref); err == nil {
			t.Fatalf("accepted %q", ref)
		}
	}
}

func TestEmptyEnvironmentIsRejected(t *testing.T) {
	t.Setenv("OPS_TEST_EMPTY", "")
	s, _ := NewLocal("")
	defer s.Close()
	if _, err := s.Get("env:OPS_TEST_EMPTY"); err == nil {
		t.Fatal("empty credential accepted")
	}
}

type unsafeStore struct{}

func (unsafeStore) Get(string) (string, error) {
	return "synthetic-partial", errors.New("synthetic-backend-credential")
}

func TestBackendErrorsNeverExposeValues(t *testing.T) {
	r, _ := redact.New(nil)
	store := WithRedaction(unsafeStore{}, r)
	value, err := store.Get("env:TEST")
	if value != "" || err == nil || strings.Contains(err.Error(), "synthetic") {
		t.Fatal("backend error leaked secret material")
	}
}
