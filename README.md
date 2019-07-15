# Quick Response Share

A desktop application to  share files on demand with mobile devices in the same local area network.

## Usage

Using the integration with your file manager sharing files with a mobile device in the same local area network couldn't be easier.
This is how it works in daily use:

* In your file manager select the files you want to share.
* Open the context menu of your selection (right click).
* Choose "Share n files"

Now you see a window with a qr-code inside and an URI underneath, followed by a button to toggle through your network interfaces. The right network interface should be already selected.

* Grab your Android Phone, Windows Phone, iPhone, Android Tablett, iPad, iPod Touch, Ubuntu Phone or whatever mobile device you have.
* Fire up your QR code scanner app (e.g. Barcode Scanner, by ZXing Team, my recommedation)
* Scan the code from your computers screen.
* Choose "Open in Browser".

Now on your mobile device you should see a list of all the files you have shared, ready for download individually by taping on the files name.

## Installation

* Download the archive, extract it and open the extracted folder in a terminal.

* Install dependencies.

```
sudo apt install python3-tornado python3-qrcode python3-cairosvg python3-qrcode python3-zeroconf
```

* Copy the icon "qrshare.png" to "/usr/share/pixmaps/"

```
sudo cp qrshare.png /usr/share/pixmaps/
```

* Copy the file "qrshare.py" to "/usr/local/bin/" and rename the file to "qrshare"

```
sudo cp qrshare.py /usr/local/bin/qrshare
```

* Add execution rights for everyone.

```
sudo chmod a+rx /usr/local/bin/qrshare
```

* Test the application.

```
qrshare
```

* Enter the command followed by file paths to share those files.

```
qrshare qrshare.py qrshare.png README.md
```

* To install the Nautilus integration, first install "python-nautilus" from the repository .

```
sudo apt-get install python-nautilus
```

* Copy the file "qrshare-nautilus.py" to "/usr/share/nautilus-python/extensions/".

```
sudo cp qrshare-nautilus.py /usr/share/nautilus-python/extensions/
```

* Make sure the file is executable

```
sudo chmod a+rx /usr/share/nautilus-python/extensions/qrshare-nautilus.py
```

* Restart Nautilus.

```
nautilus -q ; sleep 1 ; nautilus
```

If something doesn't work and you can solve the problem by your self, please tell me, so I can update the documentation. If you can't solve the problem yourself, please tell me too. I can't promise, I can help you, but at least I can try or document the problem and someone else may find a solution. ;-)
