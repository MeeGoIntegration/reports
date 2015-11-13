$(document).ready(function() {
    $("a.toggle").click(function(){
        $("div.changelog").toggle();
        return false;
    });
    $("a.pkgname").click(function(){
        $(this).parent().next("div.changelog").toggle();
        return false;
    });
    $("a.contents_toggle").click(function(){
        $(this).parent().next("div.contents").toggle();
        return false;
    });
    $("a.pkg_contents_name").click(function(){
        $(this).parent().next("div.pkg_contents").toggle();
        return false;
    });
    $("a.changelog_toggle").click(function(){
        $(this).parent().next("div.changelog").toggle();
        return false;
    });
    $("a.pname").click(function(){
        $(this).next("div.repos").toggle();
        return false;
    });
    $("a.expandcomparable").click(function(){
        $(this).next("div.comparable").toggle();
        return false;
    });
    $("a.toggle_trace").click(function(){
	$("ul.trace").toggle();
	return false;
    });
    $("a.submitreq").click(function(){
	$(this).parent().next("div.submitdetails").toggle();
	return false;
    });
    $("a.component").click(function(){
        $(this).parent().next("div.packages").toggle();
        return false;
    });
    $("a.patterns").click(function(){
        $(this).parent().next("div.patterns").toggle();
        return false;
    });

 });
