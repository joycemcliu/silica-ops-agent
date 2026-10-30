// Package secrets resolves references without exposing values in errors or logs.
package secrets

import (
	"errors"
	"io"
	"os"
	"regexp"
	"strings"
)

const MaxBytes = 64 << 10

type Store interface {
	Get(ref string) (string, error)
}

// Local resolves env:NAME and file:relative/path references. File reads are
// confined by os.Root, including symlinks. No production secret is loaded from
// the repository implicitly. Callers must supply a separate secret directory.
type Local struct {
	root *os.Root
}

func NewLocal(directory string) (*Local, error) {
	if directory == "" {
		return &Local{}, nil // Environment-only store.
	}
	root, err := os.OpenRoot(directory)
	if err != nil {
		return nil, errors.New("cannot open secret directory")
	}
	return &Local{root: root}, nil
}

func (s *Local) Close() error {
	if s.root != nil {
		return s.root.Close()
	}
	return nil
}

var variable = regexp.MustCompile(`^[A-Z_][A-Z0-9_]*$`)

func (s *Local) Get(ref string) (string, error) {
	const failure = "secret unavailable"
	scheme, name, ok := strings.Cut(ref, ":")
	if !ok || name == "" {
		return "", errors.New(failure)
	}
	switch scheme {
	case "env":
		if !variable.MatchString(name) {
			return "", errors.New(failure)
		}
		value, ok := os.LookupEnv(name)
		if !ok || len(value) == 0 || len(value) > MaxBytes {
			return "", errors.New(failure)
		}
		return value, nil
	case "file":
		if s.root == nil || !validPath(name) {
			return "", errors.New(failure)
		}
		f, err := s.root.Open(name)
		if err != nil {
			return "", errors.New(failure)
		}
		defer f.Close()
		stat, err := f.Stat()
		if err != nil || !stat.Mode().IsRegular() || stat.Mode().Perm()&0077 != 0 || stat.Size() > MaxBytes {
			return "", errors.New(failure)
		}
		data, err := io.ReadAll(io.LimitReader(f, MaxBytes+1))
		if err != nil || len(data) == 0 || len(data) > MaxBytes {
			return "", errors.New(failure)
		}
		return string(data), nil
	default:
		return "", errors.New(failure)
	}
}

func validPath(path string) bool {
	if strings.ContainsAny(path, "\\\x00\r\n") {
		return false
	}
	for _, segment := range strings.Split(path, "/") {
		if segment == "" || segment == "." || segment == ".." {
			return false
		}
	}
	return true
}
