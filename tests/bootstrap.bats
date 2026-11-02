#!/usr/bin/env bats

setup() {
    repository_root=$(cd -- "$BATS_TEST_DIRNAME/.." && pwd)
    export PATH="$repository_root/.tools/bin:$PATH"
    fixture="$BATS_TEST_TMPDIR/envs.yaml"
}

@test "the example environment passes schema validation" {
    run python3 "$repository_root/scripts/validate-envs.py" "$repository_root/envs.yaml"
    [ "$status" -eq 0 ]
}

@test "credential references cannot escape the secrets directory" {
    sed 's@test/ssh.env@../other/ssh.env@' "$repository_root/envs.yaml" > "$fixture"
    run python3 "$repository_root/scripts/validate-envs.py" "$fixture"
    [ "$status" -ne 0 ]
    sed 's@test/ssh.env@/etc/ops-agent/test/ssh.env@' "$repository_root/envs.yaml" > "$fixture"
    run python3 "$repository_root/scripts/validate-envs.py" "$fixture"
    [ "$status" -ne 0 ]
}

@test "configuration rejects inline credentials without printing their values" {
    sed '/      api:/a\      token: sensitive-fixture-value' "$repository_root/envs.yaml" > "$fixture"
    run python3 "$repository_root/scripts/validate-envs.py" "$fixture"
    [ "$status" -ne 0 ]
    [[ "$output" != *sensitive-fixture-value* ]]
}

@test "duplicate environment keys are rejected" {
    cat "$repository_root/envs.yaml" > "$fixture"
    printf '\n  test: {}\n' >> "$fixture"
    run python3 "$repository_root/scripts/validate-envs.py" "$fixture"
    [ "$status" -ne 0 ]
}

@test "SSH configuration rejects invalid ports, fingerprints, and unknown fields" {
    for replacement in 's/port: 22/port: 0/' 's/SHA256:/MD5:/' 's/port: 22/password: hidden/'; do
        sed "$replacement" "$repository_root/envs.yaml" > "$fixture"
        run python3 "$repository_root/scripts/validate-envs.py" "$fixture"
        [ "$status" -ne 0 ]
    done
}

@test "unsafe YAML tags are rejected without execution" {
    printf '!!python/object/apply:builtins.print [sensitive-fixture-value]\n' > "$fixture"
    run python3 "$repository_root/scripts/validate-envs.py" "$fixture"
    [ "$status" -ne 0 ]
    [[ "$output" != *sensitive-fixture-value* ]]
}

@test "pre-commit scans the index even when a secret is removed from the working tree" {
    mkdir "$BATS_TEST_TMPDIR/repository"
    cd "$BATS_TEST_TMPDIR/repository"
    git init -q
    printf 'Documentation only.\n' > README.md
    git add README.md
    run bash "$repository_root/.githooks/pre-commit"
    [ "$status" -eq 0 ]
    secret_prefix=ghp_
    secret_suffix=$(printf '%s' "$BATS_TEST_TMPDIR" | sha256sum)
    secret_suffix=${secret_suffix:0:36}
    printf 'access_token=%s%s\n' "$secret_prefix" "$secret_suffix" > README.md
    git add README.md
    printf 'Documentation only.\n' > README.md
    run bash "$repository_root/.githooks/pre-commit"
    [ "$status" -ne 0 ]
    [[ "$output" != *"$secret_prefix$secret_suffix"* ]]
}
