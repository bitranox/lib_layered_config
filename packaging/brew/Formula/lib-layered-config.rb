class LibLayeredConfig < Formula
  include Language::Python::Virtualenv

  desc "Rich-powered logging helpers for colorful terminal output"
  homepage "https://github.com/bitranox/lib_layered_config"
  url "https://github.com/bitranox/lib_layered_config/archive/refs/tags/v0.0.1.tar.gz"
  sha256 "<fill-me>"
  license "MIT"

  depends_on "python@3.10"

  resource "rich" do
    url "https://files.pythonhosted.org/packages/fe/75/af448d8e52bf1d8fa6a9d089ca6c07ff4453d86c65c145d0a300bb073b9b/rich-14.1.0.tar.gz"
    sha256 "e497a48b844b0320d45007cdebfeaeed8db2a4f4bcf49f15e455cfc4af11eaa8"
  end

  resource "click" do
    url "https://files.pythonhosted.org/packages/46/61/de6cd827efad202d7057d93e0fed9294b96952e188f7384832791c7b2254/click-8.3.0.tar.gz"
    sha256 "e7b8232224eba16f4ebe410c25ced9f7875cb5f3263ffc93cc3e8da705e229c4"
  end

  resource "lib_cli_exit_tools" do
    url "https://files.pythonhosted.org/packages/93/49/8361de4ae5e740a2c63833e7fedfacb4ef46d79e97c17e59f2f44206a648/lib_cli_exit_tools-1.1.1.tar.gz"
    sha256 "0611b53214052cd2b9d65aa3a0724329ccb6b1b22840c30de3e88e2faf62154c"
  end

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/lib_layered_config --version")
  end
end
