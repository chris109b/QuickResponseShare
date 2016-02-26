# QuickResponseShare
A desktop application to  share files on demand with mobile devices in the same local area network.

## Usage

Using the integration with your file manager sharing files with a mobile device in the same loacal area network couldn't be easyer.
This is how it works in dayly use:
* In your file manager select the files you want to share.
* Open the context menue of your selection (right klick).
* Choose "Quick share n files"

Now you see a window with a qrcode inside and an URI underneath, followed by a button to toggle through your network interfaces. The right network interface should be allready selected.

* Grab your Android Phone, Windows Phone, iPhone, Android Tablett, iPad, iPod Touch, Ubuntu Phone or whatever mobile device you have.
* Fire up your QR code scanner app (e.g. Barcode Scanner, by ZXing Team, my recommedation)
* Scan the code from your computers screen.
* Choose "Open in Browser".

Now on your mobile device you should see a list of all the files you have shared, ready for download individually by taping on the files name.

## Installation
* First dependencies from the repository, e.g. using a terminal enter "sudo apt-get install python-qrcode python-rsvg".
* Copy the file "qrshare.py" to "/usr/local/bin/".
* Rename the file to ""qrshare",  e.g. using a terminal enter "sudo mv /usr/local/bin/qrshare.py /usr/local/bin/qrshare".
* Add execution rights for everyone, e.g. using a terminal enter "sudo chmod a+rx /usr/local/bin/qrshare".
* Test the application, e.g. using a terminal enter "qrshare"
* Enter the command followed by file paths to share those files.
* To install the Nautilus integration, first install "python-nautilus" from the repository, e.g. using a terminal enter "sudo apt-get install python-nautilus".
* Copy the file "qrshare-nautilus.py" to "/usr/share/nautilus-python/extensions/".
* Make sure the file ist executable, e.g. using a terminal enter "sudo chmod a+rx /usr/share/nautilus-python/extensions/qrshare-nautilus.py"
* Restart nautilus, e.g. using a terminal enter "pkill nautilus && nautilus".

If it doesn't work and you can solve the  problem by your own, please tell me, so I can update the documentation. If you can't solve the problem yourself, please tell me too. I can not promise, I can help you, but at least I can try or document the problem and someone else may find a solution. ;-)
