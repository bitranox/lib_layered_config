class LibLayeredConfig < Formula
  include Language::Python::Virtualenv

  desc "Layered configuration loader for Python applications"
  homepage "https://github.com/bitranox/lib_layered_config"
  url "https://github.com/bitranox/lib_layered_config/archive/refs/tags/v0.1.1.tar.gz"
  sha256 "68cf43bdd55e2be22ca0bbd03492516446e4d1ebc9bfaa11a363e8187410c629"
  license "MIT"

  depends_on "python@3.13"

  resource "rich-click" do
    url "https://files.pythonhosted.org/packages/0c/4d/e8fcbd785a93dc5d7aef38f8aa4ade1e31b0c820eb2e8ff267056eda70b1/rich_click-1.9.2.tar.gz"
    sha256 "1c4212f05561be0cac6a9c1743e1ebcd4fe1fb1e311f9f672abfada3be649db6"
  end

  resource "lib_cli_exit_tools" do
    url "https://files.pythonhosted.org/packages/0b/d5/9078a95ee15b4147a4c92c764256468b9d18744413f45d6694a40476a626/lib_cli_exit_tools-1.5.0.tar.gz"
    sha256 "8fdacaa92a08e9f1e2bb8e70ba5bc3c9b4e786c866894ef9e0956f1fe8c1a6fd"
  end

  def install
    virtualenv_install_with_resources
  end

  test do
    output = shell_output("#{bin}/python -c 'import lib_layered_config; print(lib_layered_config.default_env_prefix(\"config-kit\"))'")
    assert_match "CONFIG_KIT", output
  end
end
