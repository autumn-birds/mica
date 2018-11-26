# -*- mode: ruby -*-
# vi: set ft=ruby :

Vagrant.configure("2") do |config|
    # The vanilla ones don't have vboxsf / virtualbox guest additions.  Probably an echo
    # of the whole debian/GNU software purity thing, which is... nice in an idealistic
    # sense.  But we need shared folders.  Fortunately they provide a box that will
    # help out with that:
    config.vm.box = "debian/contrib-testing64"
    config.vm.box_check_update = false

    # Change the host: port to where you want to connect into the proxy from outside
    config.vm.network "forwarded_port", guest: 7072, host: 7072, host_ip: "127.0.0.1"
    config.vm.network "forwarded_port", guest: 22, host: 22, host_ip: "127.0.0.1"

    # Runs once, to install dependencies and system service:
    config.vm.provision "shell", inline: <<-SHELL
        apt-get update
        apt-get install -y git python3 tf5 tmux
    SHELL
end